import json
import socket
import struct
from collections import defaultdict, deque
from typing import Any, Dict, List, Sequence, Tuple, Union

import numpy as np

from .multiagentenv import MultiAgentEnv


ShapeType = Union[int, Sequence[int], Tuple[int, ...]]


class UnityTCPEnv(MultiAgentEnv):
    """Unity TCP environment wrapper.

    Protocol: length-prefixed UTF-8 JSON request/response.
    Commands: init, reset, step, close.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 5000,
        timeout: float = 10.0,
        n_agents: int = 1,
        n_actions: int = 5,
        action_dims: Sequence[int] = None,
        state_shape: ShapeType = 9,
        obs_shape: ShapeType = 9,
        episode_limit: int = 2000,
        auto_reconnect: bool = True,
        simulate_packet_loss: bool = False,
        max_packet_loss_probability: float = 0.2,
        trajectory_entropy_enabled: bool = False,
        trajectory_entropy_scale: float = 0.01,
        trajectory_embedding_points: int = 16,
        trajectory_history_size: int = 100,
        trajectory_knn_k: int = 5,
        trajectory_map_extent: float = 1000.0,
        trajectory_noop_decision: int = 0,
        trajectory_entropy_step_clip_min: float = 0.1,
        trajectory_entropy_step_clip_max: float = 10.0,
        trajectory_entropy_progress_threshold: float = 0.15,
        trajectory_entropy_uturn_ratio_max: float = 0.35,
        trajectory_entropy_repeat_cell_ratio_max: float = 0.60,
        trajectory_road_repeat_ratio_max: float = 0.35,
        trajectory_entropy_loop_cell_size: float = 20.0,
        trajectory_entropy_activation_test_completion_rate: float = 0.85,
        trajectory_heatmap_bins: int = 20,
        trajectory_record_vehicle_id: int = 0,
        reward_stage: int = 3,
        seed: int = 0,
        train_seed_base: int = None,
        train_seed_count: int = 50,
        train_seed_repeat: int = 1,
        train_seed_window_size: int = 0,
        train_seed_window_cycles: int = 1,
        test_seed_base: int = None,
        test_seed_count: int = 20,
        randomize_target_points: bool = False,
        **kwargs: Any,
    ):
        self.host = host
        self.port = int(port)
        self.timeout = float(timeout)
        self.auto_reconnect = bool(auto_reconnect)
        self.simulate_packet_loss = bool(simulate_packet_loss)
        self.max_packet_loss_probability = float(
            np.clip(max_packet_loss_probability, 0.0, 1.0)
        )

        self.n_agents = int(n_agents)
        self.action_dims = [int(x) for x in action_dims] if action_dims is not None else None
        self._n_actions = sum(self.action_dims) if self.action_dims is not None else int(n_actions)
        self.episode_limit = int(episode_limit)

        self._state_shape = self._shape_to_tuple(state_shape)
        self._obs_shape = self._shape_to_tuple(obs_shape)

        self._socket = None
        self._request_id = 1

        self._state = self._zero_array(self._state_shape)
        self._obs = [self._zero_array(self._obs_shape) for _ in range(self.n_agents)]
        self._avail_actions = np.ones((self.n_agents, self._n_actions), dtype=np.int32)

        # TEE diagnostics are always computed. This flag only controls whether
        # the computed bonus is added to learner rewards.
        self.trajectory_entropy_enabled = bool(trajectory_entropy_enabled)
        self.trajectory_entropy_scale = float(trajectory_entropy_scale)
        self.trajectory_embedding_points = int(trajectory_embedding_points)
        self.trajectory_history_size = int(trajectory_history_size)
        self.trajectory_knn_k = int(trajectory_knn_k)
        self.trajectory_map_extent = float(trajectory_map_extent)
        self.trajectory_noop_decision = int(trajectory_noop_decision)
        self.trajectory_entropy_step_clip_min = float(trajectory_entropy_step_clip_min)
        self.trajectory_entropy_step_clip_max = float(trajectory_entropy_step_clip_max)
        self.trajectory_entropy_progress_threshold = max(1e-6, float(trajectory_entropy_progress_threshold))
        self.trajectory_entropy_uturn_ratio_max = float(np.clip(trajectory_entropy_uturn_ratio_max, 0.0, 1.0))
        self.trajectory_entropy_repeat_cell_ratio_max = float(
            np.clip(trajectory_entropy_repeat_cell_ratio_max, 0.0, 1.0)
        )
        self.trajectory_road_repeat_ratio_max = float(
            np.clip(trajectory_road_repeat_ratio_max, 0.0, 1.0)
        )
        self.trajectory_entropy_loop_cell_size = max(1e-6, float(trajectory_entropy_loop_cell_size))
        self.trajectory_entropy_activation_test_completion_rate = float(
            np.clip(trajectory_entropy_activation_test_completion_rate, 0.0, 1.0)
        )
        self.trajectory_heatmap_bins = max(1, int(trajectory_heatmap_bins))
        self.trajectory_record_vehicle_id = max(0, int(trajectory_record_vehicle_id))
        self.reward_stage = int(reward_stage)
        self.seed_value = int(seed or 0)
        self.train_seed_base = int(self.seed_value if train_seed_base is None else train_seed_base)
        self.train_seed_count = max(1, int(train_seed_count))
        self.train_seed_repeat = max(1, int(train_seed_repeat))
        self.train_seed_window_size = max(0, int(train_seed_window_size))
        if self.train_seed_window_size <= 0:
            self.train_seed_window_size = self.train_seed_count
        self.train_seed_window_size = max(1, min(self.train_seed_window_size, self.train_seed_count))
        self.train_seed_window_cycles = max(1, int(train_seed_window_cycles))
        self.test_seed_base = int(self.seed_value + 1000000 if test_seed_base is None else test_seed_base)
        self.test_seed_count = max(1, int(test_seed_count))
        self.randomize_target_points = bool(randomize_target_points)
        self._train_reset_count = 0
        self._test_reset_count = 0
        self._test_mode = False
        self._current_episode_seed = self.train_seed_base
        self._tee_reward_active = False
        self._tee_reward_activated_t_env = -1
        self._best_score_by_train_seed: Dict[int, float] = {}
        self._metric_history_by_train_seed: Dict[int, deque] = defaultdict(lambda: deque(maxlen=20))

        self._trajectory_history: Dict[Tuple[int, int], deque] = defaultdict(
            lambda: deque(maxlen=self.trajectory_history_size)
        )
        self._road_sequence_history: Dict[Tuple[int, int], deque] = defaultdict(
            lambda: deque(maxlen=self.trajectory_history_size)
        )
        self._episode_vehicle_points: Dict[int, List[Tuple[float, float]]] = defaultdict(list)
        self._episode_road_sequences_by_vehicle: Dict[int, List[str]] = defaultdict(list)
        self._episode_heatmap_points: List[Tuple[float, float]] = []
        self._episode_decision_counts_by_t: Dict[int, int] = defaultdict(int)
        self._episode_decision_ts_by_vehicle: Dict[int, List[int]] = defaultdict(list)
        self._episode_route_action_counts_by_vehicle: Dict[int, Dict[int, int]] = defaultdict(lambda: defaultdict(int))
        self._episode_nonnoop_counts_by_vehicle: Dict[int, int] = defaultdict(int)
        self._episode_road_visit_counts: Dict[str, int] = defaultdict(int)
        self._episode_last_road_by_vehicle: Dict[int, str] = {}
        self._episode_initial_vehicle_distances: Dict[int, float] = {}
        self._episode_final_vehicle_distances: Dict[int, float] = {}
        self._episode_completed_flags: Dict[int, int] = {}
        self._episode_vehicle_all_avg_seconds = 0.0
        self._episode_vehicle_completion_rate = 0.0
        self._episode_vehicle_unfinished_avg_distance = 0.0
        self._episode_step_idx = 0
        self._pending_reward_adjustments: List[float] = []
        self._pending_entropy_stats: Dict[str, float] = {}
        self._expert_actions: List[int] = [-1 for _ in range(self.n_agents)]
        self._total_env_steps = 0

        self._connect()
        init_resp = self._rpc(
            {
                "cmd": "init",
                "request_id": self._next_request_id(),
                "init": {
                    "n_agents": self.n_agents,
                    "n_actions": self._n_actions,
                    "obs_size": self.get_obs_size(),
                    "state_size": self.get_state_size(),
                    "episode_limit": self.episode_limit,
                    "simulate_packet_loss": self.simulate_packet_loss,
                    "max_packet_loss_probability": self.max_packet_loss_probability,
                    "reward_stage": self.reward_stage,
                    "seed": self.seed_value,
                    "randomize_target_points": self.randomize_target_points,
                },
            }
        )

        # Sync env sizes early so PyMARL's runner (get_env_info) sees the correct values.
        # Unity may return a different agent count or vector sizes than the constructor defaults.
        self._apply_env_info(init_resp)

        # PyMARL queries get_env_info() immediately after env construction (before the runner calls reset()).
        # If the Unity side does not echo env sizes in the init response, we still need one reset() here
        # to learn the real number of agents (and cache obs/state/avail_actions shapes) before the scheme
        # and groups are created.
        self._reset_from_unity(self.train_seed_base)

    def _apply_env_info(self, payload: Dict[str, Any]) -> None:
        if not isinstance(payload, dict):
            return

        n_agents = payload.get("n_agents")
        n_actions = payload.get("n_actions")
        obs_size = payload.get("obs_size")
        state_size = payload.get("state_size")

        try:
            if n_agents is not None:
                self.n_agents = int(n_agents)
            if n_actions is not None and self.action_dims is None:
                self._n_actions = int(n_actions)
        except Exception:
            pass

        # Unity returns sizes as flat lengths; keep them as 1D shapes.
        try:
            if obs_size is not None:
                self._obs_shape = self._shape_to_tuple(int(obs_size))
            if state_size is not None:
                self._state_shape = self._shape_to_tuple(int(state_size))
        except Exception:
            pass

        # Re-init cached arrays to match updated sizes.
        self._state = self._zero_array(self._state_shape)
        self._obs = [self._zero_array(self._obs_shape) for _ in range(self.n_agents)]
        self._avail_actions = np.ones((self.n_agents, self._n_actions), dtype=np.int32)

    def step(self, actions):
        action_list = self._decode_actions(actions)
        payload = self._rpc(
            {
                "cmd": "step",
                "request_id": self._next_request_id(),
                "actions": action_list,
            }
        )

        reward = float(payload.get("reward", 0.0))
        terminated = bool(payload.get("terminated", False))
        info = payload.get("info", {}) or {}
        if not isinstance(info, dict):
            info = {}

        self._track_episode_vehicle_metrics(payload, action_list)
        if terminated:
            self._finalize_entropy_rewards()
            info.update(self._pending_entropy_stats)
            info.update(self._build_trajectory_heatmap_info())

        self._episode_step_idx += 1
        self._total_env_steps += 1

        self._update_cache_from_payload(payload)
        return reward, terminated, info

    def get_obs(self):
        return [obs.copy() for obs in self._obs]

    def get_obs_agent(self, agent_id):
        return self._obs[int(agent_id)].copy()

    def get_obs_size(self):
        return self._shape_for_scheme(self._obs_shape)

    def get_state(self):
        return self._state.copy()

    def get_state_size(self):
        return self._shape_for_scheme(self._state_shape)

    def get_avail_actions(self):
        return self._avail_actions.copy()

    def get_expert_actions(self):
        if self.action_dims is not None:
            return np.zeros((self.n_agents, len(self.action_dims)), dtype=np.int64)
        return np.asarray(self._expert_actions, dtype=np.int64).reshape(self.n_agents, 1)

    def get_expert_action_mask(self):
        if self.action_dims is not None:
            return np.zeros((self.n_agents, len(self.action_dims)), dtype=np.float32)
        mask = np.zeros((self.n_agents, 1), dtype=np.float32)
        for idx, expert in enumerate(self._expert_actions):
            if expert <= 0 or expert >= self._n_actions:
                continue
            if idx < len(self._avail_actions):
                avail = self._avail_actions[idx]
                if expert >= len(avail) or int(avail[expert]) == 0:
                    continue
            mask[idx, 0] = 1.0
        return mask

    def get_avail_agent_actions(self, agent_id):
        return self._avail_actions[int(agent_id)].copy()

    def get_total_actions(self):
        return list(self.action_dims) if self.action_dims is not None else self._n_actions

    def reset(self):
        if self._test_mode:
            reset_seed = self.test_seed_base + (self._test_reset_count % self.test_seed_count)
            self._test_reset_count += 1
        else:
            seed_index = self._train_seed_index_for_episode(self._train_reset_count)
            reset_seed = self.train_seed_base + seed_index
            self._train_reset_count += 1
        self._current_episode_seed = int(reset_seed)
        self._reset_from_unity(reset_seed)
        return self.get_obs(), self.get_state()

    def _train_seed_index_for_episode(self, episode_idx: int) -> int:
        count = max(0, int(episode_idx))
        if self.train_seed_window_size >= self.train_seed_count and self.train_seed_window_cycles <= 1:
            return count % self.train_seed_count

        window = self.train_seed_window_size
        cycles = self.train_seed_window_cycles
        full_windows = self.train_seed_count // window
        tail = self.train_seed_count % window
        full_window_steps = window * cycles
        full_part_steps = full_windows * full_window_steps
        total_steps = full_part_steps + (tail * cycles if tail > 0 else 0)
        pos = count % max(1, total_steps)

        if pos < full_part_steps:
            window_id = pos // full_window_steps
            within_window = pos % full_window_steps
            return int(window_id * window + (within_window % window))

        if tail <= 0:
            return int(pos % self.train_seed_count)

        within_tail = pos - full_part_steps
        return int(full_windows * window + (within_tail % tail))

    def _reset_from_unity(self, reset_seed: int):
        payload = self._rpc(
            {
                "cmd": "reset",
                "request_id": self._next_request_id(),
                "seed": int(reset_seed),
            }
        )
        self._reset_episode_trajectory_state()
        self._capture_vehicle_episode_diagnostics(payload, initialize_missing=True)
        self._update_cache_from_payload(payload)

    def pop_episode_reward_adjustments(self, episode_length: int) -> Tuple[List[float], Dict[str, float]]:
        if episode_length <= 0:
            self._pending_reward_adjustments = []
            stats = self._pending_entropy_stats
            self._pending_entropy_stats = {}
            return [], stats

        out = [0.0 for _ in range(episode_length)]
        copy_len = min(len(self._pending_reward_adjustments), episode_length)
        if copy_len > 0:
            out[:copy_len] = self._pending_reward_adjustments[:copy_len]

        stats = self._pending_entropy_stats
        self._pending_reward_adjustments = []
        self._pending_entropy_stats = {}
        return out, stats

    def render(self):
        pass

    def close(self):
        # Idempotent close: safe to call multiple times and safe during reconnect paths.
        sock = self._socket
        self._socket = None

        if sock is None:
            return

        # Best-effort notify server without triggering auto-reconnect recursion.
        try:
            payload = {"cmd": "close", "request_id": self._next_request_id()}
            body = json.dumps(payload).encode("utf-8")
            header = struct.pack("<I", len(body))
            sock.sendall(header + body)
        except Exception:
            pass

        try:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            sock.close()
        except Exception:
            pass

    def seed(self):
        return None

    def save_replay(self):
        pass

    def get_stats(self):
        return {}

    def set_test_mode(self, test_mode: bool) -> None:
        test_mode = bool(test_mode)
        if test_mode and not self._test_mode:
            self._test_reset_count = 0
        self._test_mode = test_mode

    def update_tee_activation(self, t_env: int, test_completion_rate: float) -> bool:
        if not self.trajectory_entropy_enabled or self._tee_reward_active:
            return self._tee_reward_active

        try:
            rate = float(test_completion_rate)
        except Exception:
            return self._tee_reward_active

        if rate >= self.trajectory_entropy_activation_test_completion_rate:
            self._tee_reward_active = True
            self._tee_reward_activated_t_env = int(t_env)
        return self._tee_reward_active

    def _connect(self):
        try:
            self._socket = socket.create_connection((self.host, self.port), timeout=self.timeout)
            self._socket.settimeout(self.timeout)
        except Exception as e:
            raise ConnectionError(
                f"Failed to connect to Unity TCP server at {self.host}:{self.port}. "
                "Make sure the Unity Editor/Player is running and the backend TCP server is enabled "
                "(play_backend toggle or autoStart), and that the port matches env_args.port."
            ) from e

    def _ensure_connected(self):
        if self._socket is None:
            self._connect()

    def _rpc(self, message: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_connected()

        raw = None
        try:
            self._send_frame(message)
            raw = self._recv_frame()
        except Exception:
            if not self.auto_reconnect:
                raise
            self.close()
            self._connect()
            self._send_frame(message)
            raw = self._recv_frame()

        if not isinstance(raw, dict):
            raise ValueError("Unity TCP response must be a JSON object.")

        if not raw.get("ok", True):
            raise RuntimeError(f"Unity TCP error: {raw.get('error', 'unknown error')}")

        return raw

    def _send_frame(self, payload: Dict[str, Any]):
        body = json.dumps(payload).encode("utf-8")
        header = struct.pack("<I", len(body))
        self._socket.sendall(header + body)

    def _recv_frame(self) -> Dict[str, Any]:
        header = self._recv_exact(4)
        if header is None:
            raise ConnectionError("Connection closed while reading frame header.")

        length = struct.unpack("<I", header)[0]
        if length <= 0:
            raise ValueError("Invalid frame length from Unity TCP server.")

        body = self._recv_exact(length)
        if body is None:
            raise ConnectionError("Connection closed while reading frame payload.")

        return json.loads(body.decode("utf-8"))

    def _recv_exact(self, size: int):
        chunks = []
        remaining = size
        while remaining > 0:
            chunk = self._socket.recv(remaining)
            if not chunk:
                return None
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def _update_cache_from_payload(self, payload: Dict[str, Any]):
        state = payload.get("state")
        obs = payload.get("obs")
        avail_actions = payload.get("avail_actions")

        if state is None or obs is None or avail_actions is None:
            raise ValueError("Unity TCP response must include state, obs, avail_actions.")

        # Unity may decide final dimensions only after reset(). Sync shapes from payload first.
        # This prevents stale constructor/init sizes (e.g. state=(9,)) from rejecting valid data.
        if isinstance(avail_actions, list) and len(avail_actions) > 0:
            first_avail = avail_actions[0]
            first_vals = first_avail.get("values") if isinstance(first_avail, dict) else None
            if isinstance(first_vals, list) and len(first_vals) > 0:
                if self.action_dims is None:
                    self._n_actions = len(first_vals)

        if isinstance(obs, list) and len(obs) > 0:
            first_obs = obs[0]
            first_vals = first_obs.get("values") if isinstance(first_obs, dict) else None
            if isinstance(first_vals, list):
                self._obs_shape = self._shape_to_tuple(len(first_vals))

        self._state_shape = self._shape_to_tuple(int(np.asarray(state, dtype=np.float32).size))

        state_arr = np.asarray(state, dtype=np.float32)
        if state_arr.shape != self._state_shape:
            raise ValueError(f"State shape mismatch, expected {self._state_shape}, got {state_arr.shape}.")

        obs_list = []
        if not isinstance(obs, list):
            raise ValueError("obs must be a list.")

        for i, item in enumerate(obs):
            values = item.get("values") if isinstance(item, dict) else None
            arr = np.asarray(values, dtype=np.float32)
            if arr.shape != self._obs_shape:
                raise ValueError(f"Obs[{i}] shape mismatch, expected {self._obs_shape}, got {arr.shape}.")
            obs_list.append(arr)

        avail_list = []
        if not isinstance(avail_actions, list):
            raise ValueError("avail_actions must be a list.")

        for i, item in enumerate(avail_actions):
            values = item.get("values") if isinstance(item, dict) else None
            arr = np.asarray(values, dtype=np.int32)
            if arr.shape != (self._n_actions,):
                raise ValueError(f"avail_actions[{i}] shape mismatch, expected {(self._n_actions,)}, got {arr.shape}.")
            avail_list.append(arr)

        if len(obs_list) != len(avail_list):
            raise ValueError("obs and avail_actions must have the same number of agents.")

        self.n_agents = len(obs_list)
        self._state_shape = state_arr.shape
        if len(obs_list) > 0:
            self._obs_shape = obs_list[0].shape
        self._state = state_arr
        self._obs = obs_list
        self._avail_actions = np.asarray(avail_list, dtype=np.int32)

        self._expert_actions = [-1 for _ in range(self.n_agents)]
        vehicles = payload.get("vehicles")
        if isinstance(vehicles, list):
            for idx, vehicle in enumerate(vehicles):
                if idx >= self.n_agents or not isinstance(vehicle, dict):
                    continue
                expert = self._extract_expert_action(vehicle)
                if expert is None:
                    continue
                self._expert_actions[idx] = int(expert)

    def _reset_episode_trajectory_state(self) -> None:
        self._episode_vehicle_points = defaultdict(list)
        self._episode_road_sequences_by_vehicle = defaultdict(list)
        self._episode_heatmap_points = []
        self._episode_decision_counts_by_t = defaultdict(int)
        self._episode_decision_ts_by_vehicle = defaultdict(list)
        self._episode_route_action_counts_by_vehicle = defaultdict(lambda: defaultdict(int))
        self._episode_nonnoop_counts_by_vehicle = defaultdict(int)
        self._episode_road_visit_counts = defaultdict(int)
        self._episode_last_road_by_vehicle = {}
        self._episode_initial_vehicle_distances = {}
        self._episode_final_vehicle_distances = {}
        self._episode_completed_flags = {}
        self._episode_vehicle_all_avg_seconds = 0.0
        self._episode_vehicle_completion_rate = 0.0
        self._episode_vehicle_unfinished_avg_distance = 0.0
        self._episode_step_idx = 0
        self._pending_reward_adjustments = []
        self._pending_entropy_stats = {}

    def _track_episode_vehicle_metrics(self, payload: Dict[str, Any], action_list: List[int]) -> None:
        self._capture_vehicle_episode_diagnostics(payload, initialize_missing=True)
        vehicles = self._extract_vehicle_list(payload)
        if not vehicles:
            return

        t = int(self._episode_step_idx)
        for idx, vehicle in enumerate(vehicles):
            if not isinstance(vehicle, dict):
                continue

            object_type = self._extract_object_type(vehicle)
            if object_type != 0:
                continue

            pos = self._extract_xz(vehicle)
            if pos is not None:
                self._episode_heatmap_points.append(pos)

            road_id = self._extract_road_id(vehicle)
            if road_id:
                previous_road = self._episode_last_road_by_vehicle.get(idx)
                if road_id != previous_road:
                    self._episode_road_visit_counts[road_id] += 1
                    self._episode_last_road_by_vehicle[idx] = road_id
                    self._episode_road_sequences_by_vehicle[idx].append(road_id)

            decision = self._extract_decision(vehicle, action_list, idx)
            if decision is None or int(decision) == self.trajectory_noop_decision:
                continue

            decision = int(decision)
            self._episode_route_action_counts_by_vehicle[idx][decision] += 1
            self._episode_nonnoop_counts_by_vehicle[idx] += 1

            if pos is None:
                continue

            self._episode_vehicle_points[idx].append(pos)
            self._episode_decision_counts_by_t[t] += 1
            self._episode_decision_ts_by_vehicle[idx].append(t)

    def _build_trajectory_heatmap_info(self) -> Dict[str, Any]:
        bins = max(1, int(self.trajectory_heatmap_bins))
        grid = np.zeros((bins, bins), dtype=np.int32)
        if not self._episode_heatmap_points:
            return {
                "trajectory_heatmap_bins": float(bins),
                "trajectory_heatmap_point_count": 0.0,
                "trajectory_heatmap_active_cells": 0.0,
                "trajectory_heatmap_coverage": 0.0,
                "trajectory_heatmap_max_density": 0.0,
            }

        extent = max(float(self.trajectory_map_extent), 1e-6)
        half_extent = extent * 0.5
        for x, z in self._episode_heatmap_points:
            x_norm = (float(x) + half_extent) / extent
            z_norm = (float(z) + half_extent) / extent
            ix = int(np.clip(np.floor(x_norm * bins), 0, bins - 1))
            iz = int(np.clip(np.floor(z_norm * bins), 0, bins - 1))
            grid[iz, ix] += 1

        active_cells = int(np.count_nonzero(grid))
        point_count = int(len(self._episode_heatmap_points))
        return {
            "trajectory_heatmap_bins": float(bins),
            "trajectory_heatmap_point_count": float(point_count),
            "trajectory_heatmap_active_cells": float(active_cells),
            "trajectory_heatmap_coverage": float(active_cells / max(1, bins * bins)),
            "trajectory_heatmap_max_density": float(grid.max() if grid.size else 0),
        }

    def _finalize_entropy_rewards(self) -> None:
        self._pending_reward_adjustments = [0.0 for _ in range(self._episode_step_idx)]
        raw_exploration_info = self._build_raw_exploration_info()

        entropies: List[float] = []
        spatial_entropies: List[float] = []
        road_novelties: List[float] = []
        road_lcs_similarities: List[float] = []
        road_repeat_ratios: List[float] = []
        gated_entropies: List[float] = []
        vehicle_bonus_by_id: Dict[int, float] = {}
        gates: List[float] = []
        progress_gates: List[float] = []
        uturn_gates: List[float] = []
        loop_gates: List[float] = []
        uturn_ratios: List[float] = []
        repeat_cell_ratios: List[float] = []
        for vehicle_id, points in self._episode_vehicle_points.items():
            if len(points) == 0:
                continue

            embedding = self._trajectory_to_embedding(points)
            history_key = (int(self._current_episode_seed), int(vehicle_id))
            history = self._trajectory_history[history_key]
            spatial_entropy = self._knn_entropy(embedding, history)
            road_sequence = self._episode_road_sequences_by_vehicle.get(int(vehicle_id), [])
            road_history = self._road_sequence_history[history_key]
            road_novelty, road_lcs_similarity = self._road_sequence_novelty(
                road_sequence,
                road_history,
            )
            entropy = spatial_entropy * road_novelty

            gate, gate_stats = self._trajectory_entropy_gate(
                vehicle_id,
                points,
                road_sequence,
            )
            entropies.append(entropy)
            spatial_entropies.append(spatial_entropy)
            road_novelties.append(road_novelty)
            road_lcs_similarities.append(road_lcs_similarity)
            road_repeat_ratios.append(gate_stats["road_repeat_ratio"])
            gated_entropies.append(entropy * gate)
            gates.append(gate)
            progress_gates.append(gate_stats["progress_gate"])
            uturn_gates.append(gate_stats["uturn_gate"])
            loop_gates.append(gate_stats["loop_gate"])
            uturn_ratios.append(gate_stats["uturn_ratio"])
            repeat_cell_ratios.append(gate_stats["repeat_cell_ratio"])

            if gate > 0.0 and not self._test_mode:
                history.append(embedding)
                if road_sequence:
                    road_history.append(tuple(road_sequence))
            vehicle_bonus_by_id[int(vehicle_id)] = float(entropy * gate)

        if len(entropies) == 0:
            score, previous_best, improvement_gate, improvement = self._update_improvement_gate()
            self._pending_entropy_stats = {
                "entropy_reward": 0.0,
                "entropy_reward_total": 0.0,
                "entropy_reward_applied": 0.0,
                "entropy_reward_total_applied": 0.0,
                "entropy_reward_preclip": 0.0,
                "entropy_reward_postclip": 0.0,
                "entropy_reward_total_preclip": 0.0,
                "entropy_reward_total_postclip": 0.0,
                "trajectory_entropy": 0.0,
                "trajectory_entropy_raw": 0.0,
                "trajectory_spatial_entropy": 0.0,
                "trajectory_road_novelty": 0.0,
                "trajectory_road_lcs_similarity": 0.0,
                "trajectory_road_repeat_ratio": 0.0,
                "trajectory_entropy_gate": 0.0,
                "trajectory_entropy_progress_gate": 0.0,
                "trajectory_entropy_uturn_gate": 0.0,
                "trajectory_entropy_loop_gate": 0.0,
                "trajectory_entropy_uturn_ratio": 0.0,
                "trajectory_entropy_repeat_cell_ratio": 0.0,
                "trajectory_entropy_effective_vehicle_count": 0.0,
                "trajectory_decision_count": float(sum(self._episode_decision_counts_by_t.values())),
                "tee_reward_active": float(self._tee_reward_active),
                "tee_reward_activated_t_env": float(self._tee_reward_activated_t_env),
                "tee_improvement_gate": float(improvement_gate),
                "tee_episode_score": float(score),
                "tee_previous_best_score": float(previous_best),
                "tee_score_improvement": float(improvement),
                "episode_seed": float(self._current_episode_seed),
            }
            self._pending_entropy_stats.update(raw_exploration_info)
            return

        raw_episode_entropy = float(np.mean(entropies))
        episode_entropy = float(np.mean(gated_entropies))
        n_dec = int(sum(self._episode_decision_counts_by_t.values()))
        bonus_per_decision_preclip = self.trajectory_entropy_scale * episode_entropy / max(1, n_dec)
        score, previous_best, improvement_gate, improvement = self._update_improvement_gate()
        apply_bonus = (
            self.trajectory_entropy_enabled
            and self._tee_reward_active
            and not self._test_mode
            and improvement_gate > 0.0
        )

        total_bonus_preclip = 0.0
        total_bonus_postclip = 0.0
        for vehicle_id, vehicle_entropy in vehicle_bonus_by_id.items():
            decision_ts = self._episode_decision_ts_by_vehicle.get(vehicle_id, [])
            if not decision_ts:
                continue

            vehicle_bonus_per_decision_preclip = (
                self.trajectory_entropy_scale * float(vehicle_entropy) / max(1, len(decision_ts))
            )
            for t in decision_ts:
                if not (0 <= t < len(self._pending_reward_adjustments)):
                    continue
                step_bonus_preclip = vehicle_bonus_per_decision_preclip
                step_bonus_postclip = float(
                    np.clip(
                        step_bonus_preclip,
                        self.trajectory_entropy_step_clip_min,
                        self.trajectory_entropy_step_clip_max,
                    )
                )
                if apply_bonus:
                    self._pending_reward_adjustments[t] += step_bonus_postclip
                total_bonus_preclip += step_bonus_preclip
                total_bonus_postclip += step_bonus_postclip

        bonus_per_decision_postclip = total_bonus_postclip / max(1, n_dec)
        total_bonus_applied = total_bonus_postclip if apply_bonus else 0.0
        bonus_per_decision_applied = total_bonus_applied / max(1, n_dec)

        self._pending_entropy_stats = {
            # Backward-compatible keys report the computed TEE value. The *_applied keys
            # show whether it was actually added to the learner reward.
            "entropy_reward": float(bonus_per_decision_postclip),
            "entropy_reward_total": float(total_bonus_postclip),
            "entropy_reward_applied": float(bonus_per_decision_applied),
            "entropy_reward_total_applied": float(total_bonus_applied),
            "entropy_reward_preclip": float(bonus_per_decision_preclip),
            "entropy_reward_postclip": float(bonus_per_decision_postclip),
            "entropy_reward_total_preclip": float(total_bonus_preclip),
            "entropy_reward_total_postclip": float(total_bonus_postclip),
            "trajectory_entropy": float(episode_entropy),
            "trajectory_entropy_raw": float(raw_episode_entropy),
            "trajectory_spatial_entropy": float(
                np.mean(spatial_entropies) if spatial_entropies else 0.0
            ),
            "trajectory_road_novelty": float(
                np.mean(road_novelties) if road_novelties else 0.0
            ),
            "trajectory_road_lcs_similarity": float(
                np.mean(road_lcs_similarities) if road_lcs_similarities else 0.0
            ),
            "trajectory_road_repeat_ratio": float(
                np.mean(road_repeat_ratios) if road_repeat_ratios else 0.0
            ),
            "trajectory_entropy_gate": float(np.mean(gates) if gates else 0.0),
            "trajectory_entropy_progress_gate": float(np.mean(progress_gates) if progress_gates else 0.0),
            "trajectory_entropy_uturn_gate": float(np.mean(uturn_gates) if uturn_gates else 0.0),
            "trajectory_entropy_loop_gate": float(np.mean(loop_gates) if loop_gates else 0.0),
            "trajectory_entropy_uturn_ratio": float(np.mean(uturn_ratios) if uturn_ratios else 0.0),
            "trajectory_entropy_repeat_cell_ratio": float(
                np.mean(repeat_cell_ratios) if repeat_cell_ratios else 0.0
            ),
            "trajectory_entropy_effective_vehicle_count": float(sum(gates)),
            "trajectory_decision_count": float(n_dec),
            "tee_reward_active": float(self._tee_reward_active),
            "tee_reward_activated_t_env": float(self._tee_reward_activated_t_env),
            "tee_improvement_gate": float(improvement_gate),
            "tee_episode_score": float(score),
            "tee_previous_best_score": float(previous_best),
            "tee_score_improvement": float(improvement),
            "episode_seed": float(self._current_episode_seed),
        }
        self._pending_entropy_stats.update(raw_exploration_info)

    def _build_raw_exploration_info(self) -> Dict[str, Any]:
        info: Dict[str, Any] = {}

        points = self._episode_vehicle_points.get(self.trajectory_record_vehicle_id, [])
        if points:
            embedding = self._trajectory_to_embedding(points)
            info["trajectory_embedding_16"] = [float(value) for value in embedding.tolist()]
            info["trajectory_embedding_vehicle_id"] = float(self.trajectory_record_vehicle_id)
        road_sequence = self._episode_road_sequences_by_vehicle.get(
            self.trajectory_record_vehicle_id,
            [],
        )
        if road_sequence:
            info["trajectory_road_sequence"] = [str(road_id) for road_id in road_sequence]

        road_counts = {
            str(road_id): int(count)
            for road_id, count in sorted(self._episode_road_visit_counts.items())
            if int(count) > 0
        }
        info["road_visit_counts"] = road_counts
        info["road_unique_count"] = float(len(road_counts))

        total = float(sum(road_counts.values()))
        if total > 0.0:
            probabilities = np.asarray(list(road_counts.values()), dtype=float) / total
            entropy = float(-np.sum(probabilities * np.log(probabilities + 1e-12)))
        else:
            entropy = 0.0
        info["road_visit_entropy"] = entropy
        return info

    def _update_improvement_gate(self) -> Tuple[float, float, float, float]:
        score = self._episode_improvement_score()
        metrics = self._episode_improvement_metrics(score)
        if self._test_mode:
            previous = self._best_score_by_train_seed.get(int(self._current_episode_seed), score)
            return score, previous, 0.0, 0.0

        seed = int(self._current_episode_seed)
        history = self._metric_history_by_train_seed[seed]
        previous = self._best_score_by_train_seed.get(seed)
        if previous is None:
            self._best_score_by_train_seed[seed] = score
            history.append(metrics)
            return score, score, 0.0, 0.0

        improvement_gate = self._task_improvement_gate(metrics, history, previous)
        improvement = score - previous
        if score > previous:
            self._best_score_by_train_seed[seed] = score
        history.append(metrics)
        return score, previous, float(improvement_gate), improvement

    def _episode_improvement_score(self) -> float:
        completion_rate = float(self._episode_vehicle_completion_rate)
        avg_seconds = float(self._episode_vehicle_all_avg_seconds)
        unfinished_distance = float(self._episode_vehicle_unfinished_avg_distance)
        uturn_ratio = self._episode_uturn_ratio()
        return float(
            100.0 * completion_rate
            - 0.2 * avg_seconds
            - 0.01 * unfinished_distance
            - 20.0 * uturn_ratio
        )

    def _episode_improvement_metrics(self, score: float) -> Dict[str, float]:
        return {
            "score": float(score),
            "completion_rate": float(self._episode_vehicle_completion_rate),
            "avg_seconds": float(self._episode_vehicle_all_avg_seconds),
            "unfinished_distance": float(self._episode_vehicle_unfinished_avg_distance),
            "uturn_ratio": self._episode_uturn_ratio(),
        }

    @staticmethod
    def _task_improvement_gate(metrics: Dict[str, float], history: deque, previous_best_score: float) -> float:
        if not history:
            return 0.0

        hist_completion = [float(x.get("completion_rate", 0.0)) for x in history]
        hist_seconds = [float(x.get("avg_seconds", 0.0)) for x in history]
        hist_unfinished = [float(x.get("unfinished_distance", 0.0)) for x in history]
        hist_uturn = [float(x.get("uturn_ratio", 0.0)) for x in history]

        mean_completion = float(np.mean(hist_completion)) if hist_completion else 0.0
        mean_seconds = float(np.mean(hist_seconds)) if hist_seconds else float("inf")
        mean_unfinished = float(np.mean(hist_unfinished)) if hist_unfinished else float("inf")
        mean_uturn = float(np.mean(hist_uturn)) if hist_uturn else float("inf")

        completion_ok = float(metrics["completion_rate"]) + 1e-6 >= mean_completion
        uturn_ok = float(metrics["uturn_ratio"]) <= mean_uturn + 1e-6
        distance_better = float(metrics["unfinished_distance"]) + 1e-6 < mean_unfinished
        time_better = float(metrics["avg_seconds"]) + 1e-6 < mean_seconds
        score_better = float(metrics["score"]) > float(previous_best_score) + 1e-6

        if completion_ok and uturn_ok and (distance_better or time_better or score_better):
            return 1.0
        return 0.0

    def _capture_vehicle_episode_diagnostics(self, payload: Dict[str, Any], initialize_missing: bool) -> None:
        info = payload.get("info") if isinstance(payload, dict) else None
        if not isinstance(info, dict):
            return

        self._episode_vehicle_all_avg_seconds = self._read_info_float(
            info, "vehicle_all_avg_seconds", self._episode_vehicle_all_avg_seconds
        )
        self._episode_vehicle_completion_rate = self._read_info_float(
            info, "vehicle_completion_rate", self._episode_vehicle_completion_rate
        )
        self._episode_vehicle_unfinished_avg_distance = self._read_info_float(
            info, "vehicle_unfinished_avg_distance", self._episode_vehicle_unfinished_avg_distance
        )

        distances = info.get("vehicle_final_distances")
        if isinstance(distances, list):
            for idx, value in enumerate(distances):
                try:
                    distance = float(value)
                except Exception:
                    continue
                if distance < 0.0 or not np.isfinite(distance):
                    continue
                self._episode_final_vehicle_distances[idx] = distance
                if initialize_missing and idx not in self._episode_initial_vehicle_distances:
                    self._episode_initial_vehicle_distances[idx] = distance

        flags = info.get("vehicle_completed_flags")
        if isinstance(flags, list):
            for idx, value in enumerate(flags):
                try:
                    self._episode_completed_flags[idx] = int(value)
                except Exception:
                    continue

    @staticmethod
    def _read_info_float(info: Dict[str, Any], key: str, default: float) -> float:
        try:
            value = float(info.get(key, default))
        except Exception:
            return float(default)
        if not np.isfinite(value):
            return float(default)
        return value

    def _trajectory_entropy_gate(
        self,
        vehicle_id: int,
        points: List[Tuple[float, float]],
        road_sequence: Sequence[str],
    ) -> Tuple[float, Dict[str, float]]:
        progress_gate = self._trajectory_progress_gate(vehicle_id)
        uturn_ratio = self._vehicle_uturn_ratio(vehicle_id)
        uturn_gate = self._upper_ratio_gate(uturn_ratio, self.trajectory_entropy_uturn_ratio_max)
        repeat_cell_ratio = self._repeat_cell_ratio(points)
        spatial_loop_gate = self._upper_ratio_gate(
            repeat_cell_ratio,
            self.trajectory_entropy_repeat_cell_ratio_max,
        )
        road_repeat_ratio = self._road_repeat_ratio(road_sequence)
        road_loop_gate = self._upper_ratio_gate(
            road_repeat_ratio,
            self.trajectory_road_repeat_ratio_max,
        )
        loop_gate = min(spatial_loop_gate, road_loop_gate)
        gate = float(np.clip(progress_gate * uturn_gate * loop_gate, 0.0, 1.0))
        return gate, {
            "progress_gate": float(progress_gate),
            "uturn_gate": float(uturn_gate),
            "loop_gate": float(loop_gate),
            "uturn_ratio": float(uturn_ratio),
            "repeat_cell_ratio": float(repeat_cell_ratio),
            "road_repeat_ratio": float(road_repeat_ratio),
        }

    def _trajectory_progress_gate(self, vehicle_id: int) -> float:
        if int(self._episode_completed_flags.get(vehicle_id, 0)) == 1:
            return 1.0

        initial = self._episode_initial_vehicle_distances.get(vehicle_id)
        final = self._episode_final_vehicle_distances.get(vehicle_id)
        if initial is None or final is None:
            return 0.0
        if initial <= 1e-6 or final < 0.0:
            return 0.0

        progress_ratio = (float(initial) - float(final)) / max(float(initial), 1e-6)
        return float(np.clip(progress_ratio / self.trajectory_entropy_progress_threshold, 0.0, 1.0))

    def _vehicle_uturn_ratio(self, vehicle_id: int) -> float:
        nonnoop = int(self._episode_nonnoop_counts_by_vehicle.get(vehicle_id, 0))
        if nonnoop <= 0:
            return 0.0
        uturn = int(self._episode_route_action_counts_by_vehicle.get(vehicle_id, {}).get(4, 0))
        return float(np.clip(uturn / max(1, nonnoop), 0.0, 1.0))

    def _episode_uturn_ratio(self) -> float:
        active_vehicle_ids = [
            int(vehicle_id)
            for vehicle_id, count in self._episode_nonnoop_counts_by_vehicle.items()
            if int(count) > 0
        ]
        if not active_vehicle_ids:
            return 0.0
        ratios = [self._vehicle_uturn_ratio(vehicle_id) for vehicle_id in active_vehicle_ids]
        return float(np.mean(ratios))

    def _repeat_cell_ratio(self, points: List[Tuple[float, float]]) -> float:
        if not points:
            return 0.0

        cell_size = self.trajectory_entropy_loop_cell_size
        cells = set()
        for x, z in points:
            cells.add((int(np.floor(float(x) / cell_size)), int(np.floor(float(z) / cell_size))))
        return float(np.clip(1.0 - (len(cells) / max(1, len(points))), 0.0, 1.0))

    @staticmethod
    def _road_repeat_ratio(road_sequence: Sequence[str]) -> float:
        sequence = [str(road_id) for road_id in road_sequence if str(road_id)]
        if not sequence:
            return 0.0
        return float(
            np.clip(
                1.0 - (len(set(sequence)) / max(1, len(sequence))),
                0.0,
                1.0,
            )
        )

    @classmethod
    def _road_sequence_novelty(
        cls,
        road_sequence: Sequence[str],
        history: Sequence[Sequence[str]],
    ) -> Tuple[float, float]:
        sequence = tuple(str(road_id) for road_id in road_sequence if str(road_id))
        if not sequence:
            return 0.0, 1.0
        if not history:
            return 1.0, 0.0

        max_similarity = 0.0
        for old_sequence in history:
            old = tuple(str(road_id) for road_id in old_sequence if str(road_id))
            if not old:
                continue
            lcs_length = cls._lcs_length(sequence, old)
            similarity = lcs_length / max(1, max(len(sequence), len(old)))
            max_similarity = max(max_similarity, float(similarity))
        return float(np.clip(1.0 - max_similarity, 0.0, 1.0)), float(
            np.clip(max_similarity, 0.0, 1.0)
        )

    @staticmethod
    def _lcs_length(left: Sequence[str], right: Sequence[str]) -> int:
        if len(left) < len(right):
            left, right = right, left
        previous = [0] * (len(right) + 1)
        for left_value in left:
            current = [0]
            for index, right_value in enumerate(right, start=1):
                if left_value == right_value:
                    current.append(previous[index - 1] + 1)
                else:
                    current.append(max(previous[index], current[index - 1]))
            previous = current
        return int(previous[-1])

    @staticmethod
    def _upper_ratio_gate(value: float, allowed_max: float) -> float:
        value = float(np.clip(value, 0.0, 1.0))
        allowed_max = float(np.clip(allowed_max, 0.0, 1.0))
        if value <= allowed_max:
            return 1.0
        if allowed_max >= 1.0:
            return 1.0
        return float(np.clip(1.0 - ((value - allowed_max) / max(1e-6, 1.0 - allowed_max)), 0.0, 1.0))

    def _extract_vehicle_list(self, payload: Dict[str, Any]) -> List[Any]:
        candidates: List[Any] = []
        info = payload.get("info")
        if isinstance(info, dict):
            candidates.append(info)
        candidates.append(payload)

        keys = ("vehicles", "vehicle_list", "cars", "objects", "agents")
        for container in candidates:
            for key in keys:
                value = container.get(key) if isinstance(container, dict) else None
                if isinstance(value, list):
                    return value
        return []

    @staticmethod
    def _extract_object_type(vehicle: Dict[str, Any]) -> Union[int, None]:
        for key in ("ObjectType", "object_type", "type", "Type"):
            if key in vehicle:
                try:
                    return int(vehicle[key])
                except Exception:
                    return None
        return None

    def _extract_decision(self, vehicle: Dict[str, Any], action_list: List[int], idx: int) -> Union[int, None]:
        for key in ("decision", "Decision", "action", "Action"):
            if key in vehicle:
                try:
                    return int(vehicle[key])
                except Exception:
                    return None

        # Fallback: use PyMARL action list if Unity payload does not echo per-vehicle decision.
        # In multi-head mode actions are flattened as [route0, signal0, route1, signal1, ...].
        if self.action_dims is not None:
            flat_idx = idx * len(self.action_dims)
            if 0 <= flat_idx < len(action_list):
                return int(action_list[flat_idx])
            return None

        if 0 <= idx < len(action_list):
            return int(action_list[idx])
        return None

    @staticmethod
    def _extract_expert_action(vehicle: Dict[str, Any]) -> Union[int, None]:
        for key in ("expert_action", "ExpertAction", "expertAction"):
            if key in vehicle:
                try:
                    return int(vehicle[key])
                except Exception:
                    return None
        return None

    @staticmethod
    def _extract_road_id(vehicle: Dict[str, Any]) -> Union[str, None]:
        for key in ("road_id", "roadId", "currentRoadId", "current_road_id"):
            value = vehicle.get(key)
            if value is not None:
                road_id = str(value).strip()
                return road_id if road_id else None
        return None

    @staticmethod
    def _extract_xz(vehicle: Dict[str, Any]) -> Union[Tuple[float, float], None]:
        if "position" in vehicle and isinstance(vehicle["position"], dict):
            p = vehicle["position"]
            if "x" in p and "z" in p:
                try:
                    return float(p["x"]), float(p["z"])
                except Exception:
                    return None

        x = None
        z = None
        for key in ("x", "X", "pos_x", "position_x"):
            if key in vehicle:
                x = vehicle[key]
                break
        for key in ("z", "Z", "pos_z", "position_z"):
            if key in vehicle:
                z = vehicle[key]
                break

        if x is None or z is None:
            return None
        try:
            return float(x), float(z)
        except Exception:
            return None

    def _trajectory_to_embedding(self, points: List[Tuple[float, float]]) -> np.ndarray:
        pts = [(float(x), float(z)) for x, z in points]
        pts = self._fit_points_count(pts, self.trajectory_embedding_points)

        x0, z0 = pts[0]
        scale = self.trajectory_map_extent if self.trajectory_map_extent > 0 else 1000.0
        normalized: List[float] = []
        for x, z in pts:
            normalized.append((x - x0) / scale)
            normalized.append((z - z0) / scale)
        return np.asarray(normalized, dtype=np.float32)

    @staticmethod
    def _compress_once(points: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
        if len(points) <= 2:
            return points

        out: List[Tuple[float, float]] = [points[0]]
        i = 1
        while i < len(points) - 1:
            if i + 1 < len(points) - 1:
                x1, z1 = points[i]
                x2, z2 = points[i + 1]
                out.append(((x1 + x2) * 0.5, (z1 + z2) * 0.5))
                i += 2
            else:
                out.append(points[i])
                i += 1
        out.append(points[-1])
        return out

    @staticmethod
    def _expand_once(points: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
        if len(points) <= 1:
            return points

        out: List[Tuple[float, float]] = [points[0]]
        for i in range(len(points) - 1):
            x1, z1 = points[i]
            x2, z2 = points[i + 1]
            out.append(((x1 + x2) * 0.5, (z1 + z2) * 0.5))
            out.append(points[i + 1])
        return out

    def _fit_points_count(self, points: List[Tuple[float, float]], target: int) -> List[Tuple[float, float]]:
        if len(points) == 0:
            points = [(0.0, 0.0)]
        if len(points) == 1:
            points = [points[0], points[0]]

        pts = points
        guard = 0
        while len(pts) > target and guard < 64:
            pts = self._compress_once(pts)
            guard += 1

        guard = 0
        while len(pts) < target and guard < 64:
            pts = self._expand_once(pts)
            guard += 1

        if len(pts) > target:
            pts = pts[: target - 1] + [pts[-1]]
        elif len(pts) < target:
            pts = pts + [pts[-1]] * (target - len(pts))

        return pts

    def _knn_entropy(self, embedding: np.ndarray, history: deque) -> float:
        if len(history) == 0:
            return 0.0

        dists: List[float] = []
        for old in history:
            diff = embedding - old
            dists.append(float(np.linalg.norm(diff)))

        dists.sort()
        k = min(max(1, self.trajectory_knn_k), len(dists))
        mean_knn = float(np.mean(dists[:k]))
        return float(np.log1p(mean_knn))

    def _decode_actions(self, actions: Any) -> List[int]:
        if hasattr(actions, "detach"):
            arr = actions.detach().cpu().numpy()
        else:
            arr = np.asarray(actions)

        arr = np.asarray(arr)
        if self.action_dims is not None:
            arr = arr.reshape(-1, len(self.action_dims))
            out = []
            for row in arr.tolist():
                for head_idx, action in enumerate(row):
                    dim = self.action_dims[head_idx]
                    action = int(action)
                    if action < 0 or action >= dim:
                        raise ValueError(f"Action index out of range: {action}, expected [0, {dim - 1}].")
                    out.append(action)
            return out

        arr = arr.reshape(-1)
        out = [int(x) for x in arr.tolist()]

        for action in out:
            if action < 0 or action >= self._n_actions:
                raise ValueError(f"Action index out of range: {action}, expected [0, {self._n_actions - 1}].")

        return out

    def _next_request_id(self) -> int:
        rid = self._request_id
        self._request_id += 1
        return rid

    @staticmethod
    def _shape_to_tuple(shape: ShapeType) -> Tuple[int, ...]:
        if isinstance(shape, int):
            return (shape,)
        if isinstance(shape, tuple):
            return shape
        if isinstance(shape, list):
            return tuple(shape)
        raise TypeError(f"Unsupported shape type: {type(shape)}")

    @staticmethod
    def _shape_for_scheme(shape: Tuple[int, ...]) -> Union[int, Tuple[int, ...]]:
        if len(shape) == 1:
            return shape[0]
        return shape

    @staticmethod
    def _zero_array(shape: Tuple[int, ...]) -> np.ndarray:
        return np.zeros(shape, dtype=np.float32)
