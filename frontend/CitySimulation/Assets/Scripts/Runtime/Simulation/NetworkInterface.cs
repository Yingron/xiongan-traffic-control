using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using CitySimulation.Global;
using CitySimulation.UI.RunTime.Running;
using UnityEngine;

namespace CitySimulation.Runtime.Simulation
{
    /// <summary>
    /// TCP long-connection interface for backend integration.
    /// Protocol: length-prefixed UTF-8 JSON request/response.
    /// </summary>
    public sealed class NetworkInterface : MonoBehaviour
    {
        [Header("TCP Server")]
        [SerializeField] int port = 5000;
        [SerializeField] bool autoStart = true;
        [SerializeField] int maxMainThreadRequestsPerFrame = 8;
        [SerializeField] int requestTimeoutMs = 30000;

        TcpListener listener;
        Thread acceptThread;
        volatile bool running;

        public bool AutoStart
        {
            get => autoStart;
            set => autoStart = value;
        }

        public bool IsServerRunning => running;

        public void SetServerEnabled(bool enabled)
        {
            autoStart = enabled;

            if (!Application.isPlaying)
            {
                return;
            }

            if (enabled)
            {
                StartServer();
            }
            else
            {
                StopServer();
            }
        }

        readonly ConcurrentQueue<PendingRequest> pendingRequests = new ConcurrentQueue<PendingRequest>();
        readonly List<ClientSession> sessions = new List<ClientSession>();
        readonly object sessionLock = new object();

        FunctionInterface functionInterface;

        int initNAgents = -1;
        int initObsSize = -1;
        int initStateSize = -1;
        int backendSeed = 0;
        bool randomizeTargetPoints;
        int resetCount;

        void Awake()
        {
            functionInterface = new FunctionInterface();

            // Allow overriding port/autostart from command line for built players.
            // Examples:
            //   -port 5000
            //   --port 5000
            //   --port=5000
            // Note: Unity Editor Play Mode can also receive args when launching the editor.
            TryApplyCommandLineArgs();
        }

        void Start()
        {
            if (autoStart)
            {
                StartServer();
            }
        }

        void TryApplyCommandLineArgs()
        {
            string[] args;
            try
            {
                args = Environment.GetCommandLineArgs();
            }
            catch
            {
                return;
            }

            for (int i = 0; i < args.Length; i++)
            {
                string a = args[i];
                if (string.IsNullOrWhiteSpace(a))
                {
                    continue;
                }

                if (a.Equals("-port", StringComparison.OrdinalIgnoreCase) || a.Equals("--port", StringComparison.OrdinalIgnoreCase))
                {
                    if (i + 1 < args.Length && int.TryParse(args[i + 1], out int p) && p > 0 && p <= 65535)
                    {
                        port = p;
                    }
                    continue;
                }

                if (a.StartsWith("--port=", StringComparison.OrdinalIgnoreCase))
                {
                    var val = a.Substring("--port=".Length);
                    if (int.TryParse(val, out int p) && p > 0 && p <= 65535)
                    {
                        port = p;
                    }
                    continue;
                }
            }
        }

        void Update()
        {
            int budget = Mathf.Max(1, maxMainThreadRequestsPerFrame);
            for (int i = 0; i < budget; i++)
            {
                if (!pendingRequests.TryDequeue(out var pending))
                {
                    break;
                }

                try
                {
                    pending.Response = HandleRequest(pending.Request);
                }
                catch (Exception ex)
                {
                    pending.Response = new ResponseEnvelope
                    {
                        request_id = pending.Request?.request_id ?? 0,
                        ok = false,
                        error = ex.Message,
                    };
                }
                finally
                {
                    pending.Done.Set();
                }
            }
        }

        void OnDestroy()
        {
            StopServer();
        }

        public void StartServer()
        {
            if (running)
            {
                return;
            }

            try
            {
                listener = new TcpListener(IPAddress.Loopback, port);
                listener.Start();

                running = true;
                acceptThread = new Thread(AcceptLoop)
                {
                    IsBackground = true,
                    Name = "NetworkInterface-Accept"
                };
                acceptThread.Start();

                Debug.Log($"[NetworkInterface] TCP server started on 127.0.0.1:{port}");
            }
            catch (Exception ex)
            {
                running = false;
                try { listener?.Stop(); } catch { }
                listener = null;
                Debug.LogError($"[NetworkInterface] Failed to start TCP server on 127.0.0.1:{port}: {ex.Message}");
            }
        }

        public void StopServer()
        {
            running = false;

            try
            {
                listener?.Stop();
            }
            catch { }

            lock (sessionLock)
            {
                for (int i = 0; i < sessions.Count; i++)
                {
                    sessions[i]?.Close();
                }
                sessions.Clear();
            }

            try
            {
                if (acceptThread != null && acceptThread.IsAlive)
                {
                    acceptThread.Join(500);
                }
            }
            catch { }

            functionInterface?.Release();
            Debug.Log("[NetworkInterface] TCP server stopped.");
        }

        void AcceptLoop()
        {
            while (running)
            {
                try
                {
                    var client = listener.AcceptTcpClient();
                    client.NoDelay = true;

                    var session = new ClientSession(client, this);
                    lock (sessionLock)
                    {
                        sessions.Add(session);
                    }
                    session.Start();
                }
                catch (SocketException)
                {
                    if (!running)
                    {
                        return;
                    }
                }
                catch (Exception ex)
                {
                    Debug.LogWarning($"[NetworkInterface] AcceptLoop error: {ex.Message}");
                }
            }
        }

        ResponseEnvelope EnqueueAndWait(RequestEnvelope request)
        {
            var pending = new PendingRequest
            {
                Request = request,
                Done = new ManualResetEventSlim(false)
            };

            pendingRequests.Enqueue(pending);

            bool completed = pending.Done.Wait(requestTimeoutMs);
            if (!completed)
            {
                return new ResponseEnvelope
                {
                    request_id = request?.request_id ?? 0,
                    ok = false,
                    error = "Request timeout on Unity main thread"
                };
            }

            return pending.Response ?? new ResponseEnvelope
            {
                request_id = request?.request_id ?? 0,
                ok = false,
                error = "No response generated"
            };
        }

        ResponseEnvelope HandleRequest(RequestEnvelope req)
        {
            if (req == null || string.IsNullOrEmpty(req.cmd))
            {
                return ErrorResponse(req, "Invalid request: missing cmd");
            }

            string cmd = req.cmd.Trim().ToLowerInvariant();
            return cmd switch
            {
                "init" => HandleInit(req),
                "reset" => HandleReset(req),
                "step" => HandleStep(req),
                "close" => HandleClose(req),
                "ping" => new ResponseEnvelope { request_id = req.request_id, ok = true },
                _ => ErrorResponse(req, $"Unsupported cmd: {req.cmd}")
            };
        }

        ResponseEnvelope HandleInit(RequestEnvelope req)
        {
            functionInterface.Init();

            if (req.init != null)
            {
                initNAgents = req.init.n_agents;
                initObsSize = req.init.obs_size;
                initStateSize = req.init.state_size;

                ApplyBackendPacketLossOverride(
                    req.init.simulate_packet_loss,
                    req.init.max_packet_loss_probability);
                functionInterface.SetRewardStage(req.init.reward_stage);
                backendSeed = req.init.seed;
                randomizeTargetPoints = req.init.randomize_target_points;
                resetCount = 0;
            }

            return BuildEnvInfoResponse(req.request_id);
        }

        void ApplyBackendPacketLossOverride(bool enabled, float maxPacketLossProbability)
        {
            SimulationConfig.RuntimeObservationDelayOverrideActive = true;
            SimulationConfig.RuntimeObservationDelayOverrideValue = enabled;
            SimulationConfig.RuntimeObservationDelayEnabled = enabled;
            SimulationConfig.RuntimeObservationMaxPacketLossProbability =
                Mathf.Clamp01(maxPacketLossProbability);

            var binder = FindObjectOfType<RuntimeNoiseSliderBinder>(includeInactive: true);
            if (binder != null)
            {
                binder.ApplyBackendOverride(enabled);
            }

            Debug.Log(
                $"[NetworkInterface] Packet-loss simulation override from backend init = {enabled}, "
                + $"maxProbability={SimulationConfig.RuntimeObservationMaxPacketLossProbability:F3}");
        }

        ResponseEnvelope HandleReset(RequestEnvelope req)
        {
            string mapId = string.IsNullOrEmpty(req.map_id) ? "xiongan_30" : req.map_id;
            int resetSeed = req.seed != 0 ? req.seed : backendSeed + resetCount;
            resetCount++;
            functionInterface.Reset(mapId, randomizeTargetPoints, resetSeed);

            return BuildTransitionResponse(req.request_id, reward: 0f);
        }

        ResponseEnvelope HandleStep(RequestEnvelope req)
        {
            functionInterface.Init();
            functionInterface.ApplyDecision(req.actions);
            functionInterface.Step();

            return BuildTransitionResponse(req.request_id, functionInterface.GetCurrentStepReward());
        }

        ResponseEnvelope HandleClose(RequestEnvelope req)
        {
            functionInterface.Release();
            return new ResponseEnvelope
            {
                request_id = req.request_id,
                ok = true,
            };
        }

        ResponseEnvelope BuildTransitionResponse(int requestId, float reward)
        {
            var obs = functionInterface.GetObs();
            var avail = functionInterface.GetAvailActions();
            var vehicles = functionInterface.GetVehicleTrackInfos();
            int obsSize = functionInterface.GetObsSize();
            int stateSize = ResolveStateSize(obsSize, obs?.Count ?? 0);
            float[] state = BuildState(obs, stateSize);

            bool timeLimit = functionInterface.IsTimeLimitTerminal();
            functionInterface.GetEpisodeVehicleCompletionStats(
                out float allAvgSeconds,
                out float completionRate,
                out int vehicleCompletedCount,
                out int vehicleTotalCount,
                out int vehicleUnfinishedCount,
                out float vehicleUnfinishedAvgDistance,
                out float vehicleUnfinishedMaxDistance);
            functionInterface.GetEpisodeArrivalTimeStats(
                out float completedArrivalTimeMean,
                out float completedArrivalTimeStd,
                out float completedArrivalTimeP95,
                out float completedArrivalTimeMax);
            int vehicleTimeoutCount = timeLimit ? vehicleUnfinishedCount : 0;
            float vehicleTimeoutRate = vehicleTotalCount > 0
                ? (float)vehicleTimeoutCount / vehicleTotalCount
                : 0f;
            int trafficNoOperationCount = 0;
            int trafficSwitchNowCount = 0;
            int trafficKeepCount = 0;
            int trafficExtendCount = 0;
            int trafficAcceptedExtendCount = 0;
            GameServices.TrafficService?.GetEpisodeTrafficControlStats(
                out trafficNoOperationCount,
                out trafficSwitchNowCount,
                out trafficKeepCount,
                out trafficExtendCount,
                out trafficAcceptedExtendCount);
            float emergencyRedWaitSecondsTotal = 0f;
            float emergencyRedWaitSecondsMean = 0f;
            float emergencyGreenExposureSecondsTotal = 0f;
            float emergencyGreenTimeRatio = 0f;
            GameServices.TrafficService?.GetEpisodeEmergencySignalStats(
                vehicleTotalCount,
                out emergencyRedWaitSecondsTotal,
                out emergencyRedWaitSecondsMean,
                out emergencyGreenExposureSecondsTotal,
                out emergencyGreenTimeRatio);
            functionInterface.GetEpisodeObservationDelayStats(
                out int observationSendCount,
                out int staleObservationCount,
                out float staleObservationRatio,
                out float packetLossProbabilityMean,
                out float packetLossProbabilityP95,
                out float observationAgeStepsMean,
                out float observationAgeStepsP95,
                out float observationAgeSecondsMean,
                out float observationAgeSecondsP95);
            functionInterface.GetPerVehicleDiagnostics(
                out string[] vehicleIds,
                out float[] vehicleFinalDistances,
                out int[] vehicleCompletedFlags,
                out int[] vehicleDecisionWindowCounts,
                out int[] vehicleNonNoopActionCounts,
                out int[] vehicleStraightActionCounts,
                out int[] vehicleLeftActionCounts,
                out int[] vehicleRightActionCounts,
                out int[] vehicleUTurnActionCounts);

            return new ResponseEnvelope
            {
                request_id = requestId,
                ok = true,
                reward = reward,
                terminated = functionInterface.IsTerminal(),
                info = new InfoPayload
                {
                    episode_limit = timeLimit,
                    vehicle_all_avg_seconds = allAvgSeconds,
                    vehicle_completion_rate = completionRate,
                    vehicle_completed_count = vehicleCompletedCount,
                    vehicle_total_count = vehicleTotalCount,
                    vehicle_unfinished_count = vehicleUnfinishedCount,
                    vehicle_unfinished_avg_distance = vehicleUnfinishedAvgDistance,
                    vehicle_unfinished_max_distance = vehicleUnfinishedMaxDistance,
                    completed_vehicle_arrival_time_mean = completedArrivalTimeMean,
                    completed_vehicle_arrival_time_std = completedArrivalTimeStd,
                    completed_vehicle_arrival_time_p95 = completedArrivalTimeP95,
                    completed_vehicle_arrival_time_max = completedArrivalTimeMax,
                    vehicle_timeout_count = vehicleTimeoutCount,
                    vehicle_timeout_rate = vehicleTimeoutRate,
                    vehicle_ids = vehicleIds,
                    vehicle_final_distances = vehicleFinalDistances,
                    vehicle_completed_flags = vehicleCompletedFlags,
                    vehicle_decision_window_counts = vehicleDecisionWindowCounts,
                    vehicle_nonnoop_action_counts = vehicleNonNoopActionCounts,
                    vehicle_straight_action_counts = vehicleStraightActionCounts,
                    vehicle_left_action_counts = vehicleLeftActionCounts,
                    vehicle_right_action_counts = vehicleRightActionCounts,
                    vehicle_uturn_action_counts = vehicleUTurnActionCounts,
                    traffic_action_noop_count = trafficNoOperationCount,
                    traffic_action_switch_count = trafficSwitchNowCount,
                    traffic_action_keep_count = trafficKeepCount,
                    traffic_action_extend_count = trafficExtendCount,
                    traffic_extend_accepted_count = trafficAcceptedExtendCount,
                    emergency_red_wait_seconds_total = emergencyRedWaitSecondsTotal,
                    emergency_red_wait_seconds_mean_per_vehicle = emergencyRedWaitSecondsMean,
                    emergency_green_exposure_seconds_total = emergencyGreenExposureSecondsTotal,
                    emergency_green_time_ratio = emergencyGreenTimeRatio,
                    observation_send_count = observationSendCount,
                    stale_observation_count = staleObservationCount,
                    stale_observation_ratio = staleObservationRatio,
                    packet_loss_probability_mean = packetLossProbabilityMean,
                    packet_loss_probability_p95 = packetLossProbabilityP95,
                    observation_age_steps_mean = observationAgeStepsMean,
                    observation_age_steps_p95 = observationAgeStepsP95,
                    observation_age_seconds_mean = observationAgeSecondsMean,
                    observation_age_seconds_p95 = observationAgeSecondsP95,
                    reward_stage = SimulationConfig.RuntimeRewardStage,
                    vehicle_step_reward = functionInterface.GetCurrentStepVehicleReward(),
                    signal_step_reward = functionInterface.GetCurrentStepSignalReward(),
                },
                n_agents = obs.Count,
                n_actions = functionInterface.GetTotalActionsSize(),
                obs_size = obsSize,
                state_size = stateSize,
                state = state,
                obs = WrapObs(obs),
                avail_actions = WrapAvail(avail),
                vehicles = WrapVehicles(vehicles),
            };
        }

        ResponseEnvelope BuildEnvInfoResponse(int requestId)
        {
            var obs = functionInterface.GetObs();
            int obsSize = functionInterface.GetObsSize();
            int stateSize = ResolveStateSize(obsSize, obs?.Count ?? 0);

            return new ResponseEnvelope
            {
                request_id = requestId,
                ok = true,
                n_agents = initNAgents > 0 ? initNAgents : obs.Count,
                n_actions = functionInterface.GetTotalActionsSize(),
                obs_size = initObsSize > 0 ? initObsSize : obsSize,
                state_size = stateSize,
            };
        }

        int ResolveStateSize(int obsSize, int nAgents)
        {
            int derived = Mathf.Max(1, obsSize) * Mathf.Max(1, nAgents);
            int requested = Mathf.Max(0, initStateSize);
            return Mathf.Max(requested, derived);
        }

        static float[] BuildState(List<float[]> obs, int stateSize)
        {
            if (stateSize <= 0)
            {
                return Array.Empty<float>();
            }

            var state = new float[stateSize];
            if (obs == null || obs.Count == 0)
            {
                return state;
            }

            int offset = 0;
            for (int i = 0; i < obs.Count; i++)
            {
                var one = obs[i];
                if (one == null)
                {
                    continue;
                }

                int copy = Mathf.Min(one.Length, stateSize - offset);
                if (copy <= 0)
                {
                    break;
                }

                Array.Copy(one, 0, state, offset, copy);
                offset += copy;
            }

            return state;
        }

        static FloatArrayDTO[] WrapObs(List<float[]> obs)
        {
            if (obs == null)
            {
                return Array.Empty<FloatArrayDTO>();
            }

            var wrapped = new FloatArrayDTO[obs.Count];
            for (int i = 0; i < obs.Count; i++)
            {
                wrapped[i] = new FloatArrayDTO { values = obs[i] ?? Array.Empty<float>() };
            }
            return wrapped;
        }

        static IntArrayDTO[] WrapAvail(List<int[]> avail)
        {
            if (avail == null)
            {
                return Array.Empty<IntArrayDTO>();
            }

            var wrapped = new IntArrayDTO[avail.Count];
            for (int i = 0; i < avail.Count; i++)
            {
                wrapped[i] = new IntArrayDTO { values = avail[i] ?? Array.Empty<int>() };
            }
            return wrapped;
        }

        static VehicleTrackDTO[] WrapVehicles(List<VehicleTrackInfo> vehicles)
        {
            if (vehicles == null)
            {
                return Array.Empty<VehicleTrackDTO>();
            }

            var wrapped = new VehicleTrackDTO[vehicles.Count];
            for (int i = 0; i < vehicles.Count; i++)
            {
                var one = vehicles[i];
                wrapped[i] = new VehicleTrackDTO
                {
                    x = one.X,
                    z = one.Z,
                    object_type = one.ObjectType,
                    decision = one.Decision,
                    expert_action = one.ExpertAction,
                    road_id = one.RoadId,
                };
            }

            return wrapped;
        }

        static ResponseEnvelope ErrorResponse(RequestEnvelope req, string error)
        {
            return new ResponseEnvelope
            {
                request_id = req?.request_id ?? 0,
                ok = false,
                error = error,
            };
        }

        sealed class ClientSession
        {
            readonly TcpClient client;
            readonly NetworkInterface owner;
            Thread recvThread;

            public ClientSession(TcpClient client, NetworkInterface owner)
            {
                this.client = client;
                this.owner = owner;
            }

            public void Start()
            {
                recvThread = new Thread(ReceiveLoop)
                {
                    IsBackground = true,
                    Name = "NetworkInterface-Client"
                };
                recvThread.Start();
            }

            public void Close()
            {
                try { client?.Close(); } catch { }
            }

            void ReceiveLoop()
            {
                try
                {
                    using var stream = client.GetStream();
                    while (owner.running && client.Connected)
                    {
                        string json = ReadFrame(stream);
                        if (string.IsNullOrEmpty(json))
                        {
                            break;
                        }

                        var req = JsonUtility.FromJson<RequestEnvelope>(json);
                        var resp = owner.EnqueueAndWait(req);
                        string respJson = JsonUtility.ToJson(resp);
                        WriteFrame(stream, respJson);

                        if (req != null && string.Equals(req.cmd, "close", StringComparison.OrdinalIgnoreCase))
                        {
                            break;
                        }
                    }
                }
                catch (IOException)
                {
                }
                catch (Exception ex)
                {
                    Debug.LogWarning($"[NetworkInterface] Client receive error: {ex.Message}");
                }
                finally
                {
                    Close();
                }
            }

            static string ReadFrame(NetworkStream stream)
            {
                var header = ReadExact(stream, 4);
                if (header == null)
                {
                    return null;
                }

                int length = BitConverter.ToInt32(header, 0);
                if (length <= 0)
                {
                    return null;
                }

                var payload = ReadExact(stream, length);
                if (payload == null)
                {
                    return null;
                }

                return Encoding.UTF8.GetString(payload);
            }

            static void WriteFrame(NetworkStream stream, string json)
            {
                var payload = Encoding.UTF8.GetBytes(json ?? "{}");
                var header = BitConverter.GetBytes(payload.Length);
                stream.Write(header, 0, header.Length);
                stream.Write(payload, 0, payload.Length);
                stream.Flush();
            }

            static byte[] ReadExact(NetworkStream stream, int size)
            {
                var buffer = new byte[size];
                int offset = 0;
                while (offset < size)
                {
                    int read = stream.Read(buffer, offset, size - offset);
                    if (read <= 0)
                    {
                        return null;
                    }

                    offset += read;
                }

                return buffer;
            }
        }

        sealed class PendingRequest
        {
            public RequestEnvelope Request;
            public ResponseEnvelope Response;
            public ManualResetEventSlim Done;
        }

        [Serializable]
        class InitPayload
        {
            public int n_agents;
            public int n_actions;
            public int obs_size;
            public int state_size;
            public int episode_limit;
            public bool simulate_packet_loss;
            public float max_packet_loss_probability;
            public int reward_stage;
            public int seed;
            public bool randomize_target_points;
        }

        [Serializable]
        class RequestEnvelope
        {
            public string cmd;
            public int request_id;
            public int[] actions;
            public int seed;
            public string map_id;
            public InitPayload init;
        }

        [Serializable]
        class FloatArrayDTO
        {
            public float[] values;
        }

        [Serializable]
        class IntArrayDTO
        {
            public int[] values;
        }

        [Serializable]
        class InfoPayload
        {
            public bool episode_limit;
            public float vehicle_all_avg_seconds;
            public float vehicle_completion_rate;
            public int vehicle_completed_count;
            public int vehicle_total_count;
            public int vehicle_unfinished_count;
            public float vehicle_unfinished_avg_distance;
            public float vehicle_unfinished_max_distance;
            public float completed_vehicle_arrival_time_mean;
            public float completed_vehicle_arrival_time_std;
            public float completed_vehicle_arrival_time_p95;
            public float completed_vehicle_arrival_time_max;
            public int vehicle_timeout_count;
            public float vehicle_timeout_rate;
            public string[] vehicle_ids;
            public float[] vehicle_final_distances;
            public int[] vehicle_completed_flags;
            public int[] vehicle_decision_window_counts;
            public int[] vehicle_nonnoop_action_counts;
            public int[] vehicle_straight_action_counts;
            public int[] vehicle_left_action_counts;
            public int[] vehicle_right_action_counts;
            public int[] vehicle_uturn_action_counts;
            public int traffic_action_noop_count;
            public int traffic_action_switch_count;
            public int traffic_action_keep_count;
            public int traffic_action_extend_count;
            public int traffic_extend_accepted_count;
            public float emergency_red_wait_seconds_total;
            public float emergency_red_wait_seconds_mean_per_vehicle;
            public float emergency_green_exposure_seconds_total;
            public float emergency_green_time_ratio;
            public int observation_send_count;
            public int stale_observation_count;
            public float stale_observation_ratio;
            public float packet_loss_probability_mean;
            public float packet_loss_probability_p95;
            public float observation_age_steps_mean;
            public float observation_age_steps_p95;
            public float observation_age_seconds_mean;
            public float observation_age_seconds_p95;
            public int reward_stage;
            public float vehicle_step_reward;
            public float signal_step_reward;
        }

        [Serializable]
        class VehicleTrackDTO
        {
            public float x;
            public float z;
            public int object_type;
            public int decision;
            public int expert_action;
            public string road_id;
        }

        [Serializable]
        class ResponseEnvelope
        {
            public int request_id;
            public bool ok = true;
            public string error;

            public int n_agents;
            public int n_actions;
            public int obs_size;
            public int state_size;

            public float reward;
            public bool terminated;

            public InfoPayload info;

            public float[] state;
            public FloatArrayDTO[] obs;
            public IntArrayDTO[] avail_actions;
            public VehicleTrackDTO[] vehicles;
        }
    }
}
