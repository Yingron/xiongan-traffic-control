import os
import sys
import numpy as np
import gymnasium as gym
from gymnasium import spaces

if 'SUMO_HOME' in os.environ:
    tools = os.path.join(os.environ['SUMO_HOME'], 'tools')
    sys.path.append(tools)
else:
    sys.exit("请设置SUMO_HOME环境变量")

import traci
import traci.constants as tc


class XionganEnv(gym.Env):
    metadata = {'render.modes': ['human', 'rgb_array']}

    PHASE_NS_STRAIGHT = 0
    PHASE_NS_LEFT = 1
    PHASE_EW_STRAIGHT = 2
    PHASE_EW_LEFT = 3

    MIN_GREEN = 15
    YELLOW_DURATION = 3

    def __init__(self, sumo_cfg_path, use_gui=False, max_steps=3600, delta_time=5):
        self.sumo_cfg_path = sumo_cfg_path
        self.use_gui = use_gui
        self.max_steps = max_steps
        self.delta_time = delta_time
        self.current_step = 0
        self.sumo_running = False

        self.tl_ids = []
        self.lane_ids = {}
        self.detector_ids = {}

        self.observation_space = spaces.Box(
            low=0, high=1, shape=(26,), dtype=np.float32
        )
        self.action_space = spaces.Discrete(4)

        self.prev_action = None
        self.prev_queue = None

    def _start_sumo(self):
        if self.sumo_running:
            return

        sumo_binary = "sumo-gui" if self.use_gui else "sumo"
        traci.start([
            sumo_binary,
            "-c", self.sumo_cfg_path,
            "--no-step-log",
            "--no-warnings",
            "--time-to-teleport", "-1"
        ])
        self.sumo_running = True
        self._init_tl_info()

    def _init_tl_info(self):
        self.tl_ids = traci.trafficlight.getIDList()
        self.lane_ids = {}
        self.detector_ids = {}

        for tl_id in self.tl_ids:
            controlled_lanes = traci.trafficlight.getControlledLanes(tl_id)
            self.lane_ids[tl_id] = controlled_lanes

    def _get_state(self):
        state = np.zeros(26, dtype=np.float32)

        if not self.tl_ids:
            return state

        tl_id = self.tl_ids[0]

        current_phase = traci.trafficlight.getPhase(tl_id)
        phase_one_hot = np.zeros(4, dtype=np.float32)
        phase_one_hot[current_phase % 4] = 1.0
        state[0:4] = phase_one_hot

        lanes = self.lane_ids.get(tl_id, [])
        if len(lanes) >= 4:
            for i, lane in enumerate(lanes[:4]):
                halting = traci.lane.getLastStepHaltingNumber(lane)
                state[4 + i] = min(halting / 50.0, 1.0)

        for i, lane in enumerate(lanes[:4]):
            wait_time = traci.lane.getLastStepVehicleNumber(lane)
            state[8 + i] = min(wait_time * 0.02, 1.0)

        for i, lane in enumerate(lanes[:4]):
            passed = traci.lane.getLastStepVehicleNumber(lane)
            state[12 + i] = min(passed / 20.0, 1.0)

        for i, lane in enumerate(lanes[:4]):
            occupancy = traci.lane.getLastStepOccupancy(lane) / 100.0
            state[16 + i] = occupancy

        sim_time = traci.simulation.getTime()
        hour = sim_time / 3600.0
        minute = (sim_time % 3600) / 60.0
        state[20] = hour / 24.0
        state[21] = minute / 60.0

        for i, lane in enumerate(lanes[:4]):
            halting = traci.lane.getLastStepHaltingNumber(lane)
            max_capacity = traci.lane.getLength(lane) / 7.5
            overflow_risk = halting / max_capacity if max_capacity > 0 else 0
            state[22 + i] = min(overflow_risk, 1.0)

        return state

    def _calculate_reward(self, state, action):
        queues = state[4:8]
        wait_times = state[8:12]
        throughput = state[12:16]
        overflow_risk = state[22:26]

        w1, w2, w3, w4, w5 = 0.1, 0.5, 0.2, 1.0, 5.0

        reward = (
            w1 * (-np.sum(queues)) +
            w2 * (-np.max(wait_times)) +
            w3 * np.sum(throughput)
        )

        if self.prev_action is not None and action != self.prev_action:
            reward += w4 * (-1)

        if np.any(overflow_risk > 0.8):
            reward += w5 * (-1)

        self.prev_action = action
        return reward

    def _apply_action(self, action):
        if not self.tl_ids:
            return

        tl_id = self.tl_ids[0]
        current_phase = traci.trafficlight.getPhase(tl_id)

        if action == current_phase:
            return

        traci.trafficlight.setPhase(tl_id, action)

    def step(self, action):
        self.current_step += 1
        done = self.current_step >= self.max_steps

        self._apply_action(action)

        for _ in range(self.delta_time):
            traci.simulationStep()

        state = self._get_state()
        reward = self._calculate_reward(state, action)

        info = {
            'step': self.current_step,
            'sim_time': traci.simulation.getTime(),
            'queue_length': np.sum(state[4:8]),
            'reward': reward
        }

        if done:
            self.close()

        return state, reward, done, False, info

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)

        if self.sumo_running:
            traci.close()
            self.sumo_running = False

        self.current_step = 0
        self.prev_action = None
        self.prev_queue = None

        self._start_sumo()
        state = self._get_state()

        return state, {}

    def close(self):
        if self.sumo_running:
            traci.close()
            self.sumo_running = False

    def render(self, mode='human'):
        if self.use_gui:
            traci.gui.screenshot("View #0", "screenshot.png")


class XionganMultiEnv(XionganEnv):
    def __init__(self, sumo_cfg_path, use_gui=False, max_steps=3600, delta_time=5):
        super().__init__(sumo_cfg_path, use_gui, max_steps, delta_time)

    def _get_state(self):
        all_states = []

        for tl_id in self.tl_ids:
            state = np.zeros(26, dtype=np.float32)

            current_phase = traci.trafficlight.getPhase(tl_id)
            phase_one_hot = np.zeros(4, dtype=np.float32)
            phase_one_hot[current_phase % 4] = 1.0
            state[0:4] = phase_one_hot

            lanes = self.lane_ids.get(tl_id, [])
            for i, lane in enumerate(lanes[:4]):
                halting = traci.lane.getLastStepHaltingNumber(lane)
                state[4 + i] = min(halting / 50.0, 1.0)

            for i, lane in enumerate(lanes[:4]):
                wait_time = traci.lane.getLastStepVehicleNumber(lane)
                state[8 + i] = min(wait_time * 0.02, 1.0)

            for i, lane in enumerate(lanes[:4]):
                passed = traci.lane.getLastStepVehicleNumber(lane)
                state[12 + i] = min(passed / 20.0, 1.0)

            for i, lane in enumerate(lanes[:4]):
                occupancy = traci.lane.getLastStepOccupancy(lane) / 100.0
                state[16 + i] = occupancy

            sim_time = traci.simulation.getTime()
            hour = sim_time / 3600.0
            minute = (sim_time % 3600) / 60.0
            state[20] = hour / 24.0
            state[21] = minute / 60.0

            for i, lane in enumerate(lanes[:4]):
                halting = traci.lane.getLastStepHaltingNumber(lane)
                max_capacity = traci.lane.getLength(lane) / 7.5
                overflow_risk = halting / max_capacity if max_capacity > 0 else 0
                state[22 + i] = min(overflow_risk, 1.0)

            all_states.append(state)

        return np.concatenate(all_states) if all_states else np.zeros(26)