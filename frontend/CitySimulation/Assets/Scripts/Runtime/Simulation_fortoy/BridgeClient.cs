using System;
using System.Collections.Generic;
using System.IO;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using CitySimulation.DTO;
using CitySimulation.Global;
using CitySimulation.Runtime.Services.Traffic;
using CitySimulation.Runtime.Services.Vehicle;
using UnityEngine;

namespace CitySimulation.Runtime.Simulation
{
    /// <summary>
    /// 真实 TCP 客户端，对接 C bridge_server。
    /// 使用 JSON 行协议：每行一条 JSON 消息（请求/响应）。
    /// 运行在后台线程，Unity 主线程通过 Poll 拉取结果。
    /// </summary>
    public sealed class BridgeClient : IDisposable
    {
        // ===================== 配置 =====================
        public string Host { get; set; } = "127.0.0.1";
        public int Port { get; set; } = 5000;
        public int ConnectTimeoutMs { get; set; } = 3000;
        public int SendTimeoutMs { get; set; } = 2000;
        public int RecvTimeoutMs { get; set; } = 2000;
        public int ReconnectIntervalMs { get; set; } = 1000;

        // ===================== 连接状态 =====================
        public enum ConnectionState
        {
            Disconnected,
            Connecting,
            Connected,
            Reconnecting,
            Error,
        }

        public ConnectionState State { get; private set; } = ConnectionState.Disconnected;
        public bool IsConnected => State == ConnectionState.Connected;
        public int RequestCount { get; private set; }
        public int ErrorCount { get; private set; }
        public float LastLatencyMs { get; private set; }

        // ===================== 事件 =====================
        public event Action<ConnectionState> OnStateChanged;
        public event Action<int> OnResponseReceived;

        // ===================== 内部 =====================
        private TcpClient _tcpClient;
        private StreamReader _reader;
        private StreamWriter _writer;
        private Thread _recvThread;
        private volatile bool _running;
        private readonly AutoResetEvent _responseEvent = new(false);

        private readonly Queue<BridgeResponse> _pendingResponses = new();
        private readonly object _lock = new();
        private int _requestIdCounter;

        // 最新状态（供UI显示）
        public string LastError { get; private set; }
        public DateTime LastRequestTime { get; private set; } = DateTime.MinValue;
        public DateTime LastResponseTime { get; private set; } = DateTime.MinValue;

        // ===================== 生命周期 =====================
        public void Start()
        {
            if (_running) return;
            _running = true;
            _recvThread = new Thread(RecvLoop)
            {
                IsBackground = true,
                Name = "BridgeClient-Recv"
            };
            _recvThread.Start();
            ConnectAsync();
        }

        public void Stop()
        {
            _running = false;
            Disconnect();
            _recvThread?.Join(1000);
        }

        public void Dispose()
        {
            Stop();
            _responseEvent.Dispose();
        }

        // ===================== 连接管理 =====================
        private void SetState(ConnectionState state)
        {
            if (State != state)
            {
                State = state;
                OnStateChanged?.Invoke(state);
            }
        }

        private void ConnectAsync()
        {
            if (!_running) return;
            SetState(ConnectionState.Connecting);

            try
            {
                _tcpClient = new TcpClient();
                _tcpClient.ReceiveTimeout = RecvTimeoutMs;
                _tcpClient.SendTimeout = SendTimeoutMs;
                _tcpClient.Connect(Host, Port);

                var stream = _tcpClient.GetStream();
                _writer = new StreamWriter(stream, Encoding.UTF8) { AutoFlush = true };
                _reader = new StreamReader(stream, Encoding.UTF8);

                SetState(ConnectionState.Connected);
                Debug.Log($"[BridgeClient] Connected to {Host}:{Port}");
            }
            catch (Exception ex)
            {
                LastError = ex.Message;
                SetState(ConnectionState.Reconnecting);
                Debug.LogWarning($"[BridgeClient] Connect failed: {ex.Message}. Retrying in {ReconnectIntervalMs}ms...");
            }
        }

        private void Disconnect()
        {
            try { _writer?.Close(); } catch { }
            try { _reader?.Close(); } catch { }
            try { _tcpClient?.Close(); } catch { }
            _writer = null;
            _reader = null;
            _tcpClient = null;
            SetState(ConnectionState.Disconnected);
        }

        private void RecvLoop()
        {
            while (_running)
            {
                if (!IsConnected)
                {
                    Thread.Sleep(ReconnectIntervalMs);
                    ConnectAsync();
                    if (!IsConnected) continue;
                }

                try
                {
                    string line = _reader.ReadLine();
                    if (line == null)
                    {
                        throw new IOException("Connection closed by server");
                    }

                    if (!string.IsNullOrEmpty(line))
                    {
                        var response = ParseResponse(line);
                        lock (_lock)
                        {
                            _pendingResponses.Enqueue(response);
                        }
                        LastResponseTime = DateTime.Now;
                        OnResponseReceived?.Invoke(response.requestId);
                        _responseEvent.Set();
                    }
                }
                catch (Exception ex)
                {
                    ErrorCount++;
                    LastError = ex.Message;
                    Debug.LogWarning($"[BridgeClient] Recv error: {ex.Message}");
                    Disconnect();
                }
            }
        }

        // ===================== 请求/响应 =====================
        /// <summary>
        /// 发送决策请求（车辆 + 交通灯观测），返回决策结果。
        /// 同步等待响应（带超时）。
        /// </summary>
        public BridgeResponse SendDecisionRequest(
            List<VehicleObverse> vehicleObserves,
            List<TrafficObverse> trafficObserves)
        {
            if (!IsConnected)
            {
                return BridgeResponse.CreateFallback(vehicleObserves?.Count ?? 0, trafficObserves?.Count ?? 0);
            }

            int requestId = Interlocked.Increment(ref _requestIdCounter);
            var request = new BridgeRequest
            {
                request_id = requestId,
                timestamp = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(),
                vehicle_obs = vehicleObserves ?? new List<VehicleObverse>(),
                traffic_obs = trafficObserves ?? new List<TrafficObverse>(),
            };

            try
            {
                string json = SerializeRequest(request);
                _writer.WriteLine(json);
                _writer.Flush();
                RequestCount++;
                LastRequestTime = DateTime.Now;

                // 等待响应（最多 SendTimeoutMs + RecvTimeoutMs）
                bool gotResponse = _responseEvent.WaitOne(SendTimeoutMs + RecvTimeoutMs);
                if (!gotResponse)
                {
                    ErrorCount++;
                    Debug.LogWarning($"[BridgeClient] Request #{requestId} timed out");
                    return BridgeResponse.CreateFallback(vehicleObserves?.Count ?? 0, trafficObserves?.Count ?? 0);
                }

                lock (_lock)
                {
                    if (_pendingResponses.Count > 0)
                    {
                        var response = _pendingResponses.Dequeue();
                        LastLatencyMs = (float)(DateTime.Now - LastRequestTime).TotalMilliseconds;
                        return response;
                    }
                }

                return BridgeResponse.CreateFallback(vehicleObserves?.Count ?? 0, trafficObserves?.Count ?? 0);
            }
            catch (Exception ex)
            {
                ErrorCount++;
                LastError = ex.Message;
                Debug.LogWarning($"[BridgeClient] Send error: {ex.Message}");
                Disconnect();
                return BridgeResponse.CreateFallback(vehicleObserves?.Count ?? 0, trafficObserves?.Count ?? 0);
            }
        }

        // ===================== 序列化 =====================
        private string SerializeRequest(BridgeRequest req)
        {
            var sb = new StringBuilder();
            sb.Append('{');
            sb.Append("\"request_id\":").Append(req.request_id).Append(',');
            sb.Append("\"timestamp\":").Append(req.timestamp).Append(',');

            // vehicle_obs
            sb.Append("\"vehicle_obs\":[");
            for (int i = 0; i < req.vehicle_obs.Count; i++)
            {
                if (i > 0) sb.Append(',');
                var v = req.vehicle_obs[i];
                sb.Append('{');
                sb.AppendFormat("\"px\":{0:F3},", v.PositionX);
                sb.AppendFormat("\"pz\":{0:F3},", v.PositionZ);
                sb.AppendFormat("\"sin\":{0:F4},", v.SinThetaToTarget);
                sb.AppendFormat("\"cos\":{0:F4},", v.CosThetaToTarget);
                sb.AppendFormat("\"dist\":{0:F2},", v.DistanceToTarget);
                sb.AppendFormat("\"status\":{0},", (int)v.GameStatus);
                sb.AppendFormat("\"type\":{0}", v.ObjectType);
                sb.Append('}');
            }
            sb.Append("],");

            // traffic_obs
            sb.Append("\"traffic_obs\":[");
            for (int i = 0; i < req.traffic_obs.Count; i++)
            {
                if (i > 0) sb.Append(',');
                var t = req.traffic_obs[i];
                sb.Append('{');
                sb.AppendFormat("\"g0\":{0},", t.GreenDir0);
                sb.AppendFormat("\"g1\":{0},", t.GreenDir1);
                sb.AppendFormat("\"e0\":{0},", t.EmergencyCountDir0);
                sb.AppendFormat("\"e1\":{0},", t.EmergencyCountDir1);
                sb.AppendFormat("\"cong\":{0},", t.CongestionCountInRange);
                sb.AppendFormat("\"ext\":{0},", t.AvailableExtendLeft);
                sb.AppendFormat("\"tleft\":{0:F2},", t.LightTimeLeft);
                sb.AppendFormat("\"status\":{0},", (int)t.GameStatus);
                sb.AppendFormat("\"type\":{0}", t.ObjectType);
                sb.Append('}');
            }
            sb.Append(']');
            sb.Append('}');

            return sb.ToString();
        }

        private BridgeResponse ParseResponse(string json)
        {
            var resp = new BridgeResponse();

            // 简单 JSON 解析（避免依赖 Newtonsoft）
            int idx = 0;
            SkipWhitespace(json, ref idx);
            if (idx >= json.Length || json[idx] != '{') return resp;
            idx++; // skip '{'

            while (idx < json.Length)
            {
                SkipWhitespace(json, ref idx);
                if (idx >= json.Length || json[idx] == '}') break;
                if (json[idx] == ',') { idx++; continue; }

                string key = ReadString(json, ref idx);
                SkipWhitespace(json, ref idx);
                if (idx >= json.Length || json[idx] != ':') break;
                idx++; // skip ':'
                SkipWhitespace(json, ref idx);

                switch (key)
                {
                    case "request_id":
                        resp.requestId = ReadInt(json, ref idx);
                        break;
                    case "status":
                        resp.status = ReadString(json, ref idx);
                        break;
                    case "vehicle_actions":
                        resp.vehicleActions = ReadIntArray(json, ref idx);
                        break;
                    case "traffic_actions":
                        resp.trafficActions = ReadIntArray(json, ref idx);
                        break;
                    case "message":
                        resp.message = ReadString(json, ref idx);
                        break;
                    default:
                        SkipValue(json, ref idx);
                        break;
                }
            }

            return resp;
        }

        // ===================== JSON 解析辅助 =====================
        private static void SkipWhitespace(string s, ref int i)
        {
            while (i < s.Length && char.IsWhiteSpace(s[i])) i++;
        }

        private static string ReadString(string s, ref int i)
        {
            if (i >= s.Length || s[i] != '"') return "";
            i++; // skip opening "
            int start = i;
            while (i < s.Length && s[i] != '"') i++;
            string result = s.Substring(start, i - start);
            if (i < s.Length) i++; // skip closing "
            return result;
        }

        private static int ReadInt(string s, ref int i)
        {
            SkipWhitespace(s, ref i);
            int start = i;
            if (i < s.Length && s[i] == '-') i++;
            while (i < s.Length && char.IsDigit(s[i])) i++;
            if (start == i) return 0;
            return int.Parse(s.Substring(start, i - start));
        }

        private static List<int> ReadIntArray(string s, ref int i)
        {
            var list = new List<int>();
            SkipWhitespace(s, ref i);
            if (i >= s.Length || s[i] != '[') return list;
            i++; // skip '['
            while (i < s.Length && s[i] != ']')
            {
                SkipWhitespace(s, ref i);
                if (i < s.Length && s[i] == ',') { i++; continue; }
                if (i < s.Length && s[i] == ']') break;
                list.Add(ReadInt(s, ref i));
            }
            if (i < s.Length) i++; // skip ']'
            return list;
        }

        private static void SkipValue(string s, ref int i)
        {
            SkipWhitespace(s, ref i);
            if (i >= s.Length) return;
            char c = s[i];
            if (c == '"') { ReadString(s, ref i); return; }
            if (c == '[') { int depth = 1; i++; while (i < s.Length && depth > 0) { if (s[i] == '[') depth++; else if (s[i] == ']') depth--; i++; } return; }
            if (c == '{') { int depth = 1; i++; while (i < s.Length && depth > 0) { if (s[i] == '{') depth++; else if (s[i] == '}') depth--; i++; } return; }
            // number, bool, null
            while (i < s.Length && s[i] != ',' && s[i] != '}' && s[i] != ']') i++;
        }
    }

    // ===================== 数据结构 =====================

    public class BridgeRequest
    {
        public int request_id;
        public long timestamp;
        public List<VehicleObverse> vehicle_obs;
        public List<TrafficObverse> traffic_obs;
    }

    public class BridgeResponse
    {
        public int requestId;
        public string status = "ok";
        public List<int> vehicleActions = new();
        public List<int> trafficActions = new();
        public string message = "";

        public static BridgeResponse CreateFallback(int vehicleCount, int trafficCount)
        {
            var resp = new BridgeResponse { status = "fallback" };
            for (int i = 0; i < vehicleCount; i++)
                resp.vehicleActions.Add(0); // NoOperation
            for (int i = 0; i < trafficCount; i++)
                resp.trafficActions.Add(0); // NoOperation
            return resp;
        }
    }
}
