import asyncio
import json
import os
import sys
import time
import numpy as np

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import websockets

from env.xiongan_env import XionganEnv
from training.config import ENV_CONFIG


class SimulationServer:
    def __init__(self, host='localhost', port=8765):
        self.host = host
        self.port = port
        self.env = None
        self.state = None
        self.running = False
        self.clients = set()
        self.simulation_time = 0
        self.total_vehicles = 0
        self.passed_vehicles = 0

    async def handle_client(self, websocket, path):
        print(f"Client connected: {websocket.remote_address}")
        self.clients.add(websocket)

        try:
            async for message in websocket:
                await self.handle_message(websocket, message)
        finally:
            print(f"Client disconnected: {websocket.remote_address}")
            self.clients.remove(websocket)

    async def handle_message(self, websocket, message):
        try:
            data = json.loads(message)
            
            if data.get('action') == 'start':
                await self.start_simulation()
            
            elif data.get('action') == 'stop':
                await self.stop_simulation()
            
            elif data.get('action') == 'step':
                steps = data.get('steps', 1)
                await self.run_steps(steps)
            
            elif data.get('action') == 'reset':
                await self.reset_simulation()
            
            elif data.get('action') == 'predict':
                action = data.get('action_value', 0)
                await self.execute_action(action)
            
            elif data.get('action') == 'get_state':
                state_data = self.get_state_data()
                await websocket.send(json.dumps(state_data))
            
            elif data.get('action') == 'set_scenario':
                scenario = data.get('scenario', 'morning_peak')
                await self.set_scenario(scenario)

        except json.JSONDecodeError:
            print(f"Invalid JSON message: {message}")

    async def start_simulation(self):
        if self.env is None:
            env_config = ENV_CONFIG.copy()
            env_config['use_gui'] = False
            self.env = XionganEnv(**env_config)
            self.state, _ = self.env.reset()
        
        self.running = True
        print("Simulation started")
        
        await self.broadcast_state()

    async def stop_simulation(self):
        self.running = False
        
        if self.env is not None:
            self.env.close()
            self.env = None
        
        print("Simulation stopped")

    async def reset_simulation(self):
        if self.env is not None:
            self.state, _ = self.env.reset()
            self.simulation_time = 0
            self.total_vehicles = 0
            self.passed_vehicles = 0
            await self.broadcast_state()
            print("Simulation reset")

    async def run_steps(self, steps=1):
        if self.env is None or not self.running:
            return

        for _ in range(steps):
            action = 0
            self.state, reward, done, _, info = self.env.step(action)
            self.simulation_time = info.get('sim_time', 0)
            
            if done:
                self.running = False
                break

        await self.broadcast_state()

    async def execute_action(self, action):
        if self.env is None or not self.running:
            return

        self.state, reward, done, _, info = self.env.step(action)
        self.simulation_time = info.get('sim_time', 0)
        
        if done:
            self.running = False

        await self.broadcast_state()

    async def broadcast_state(self):
        state_data = self.get_state_data()
        message = json.dumps(state_data)
        
        for client in self.clients:
            try:
                await client.send(message)
            except websockets.exceptions.ConnectionClosed:
                pass

    def get_state_data(self):
        if self.state is None:
            return {
                'timestamp': int(time.time()),
                'simulation_time': 0,
                'intersections': [],
                'vehicles': [],
                'metrics': {
                    'avg_travel_time': 0,
                    'avg_queue_length': 0,
                    'throughput': 0,
                    'total_vehicles': 0,
                    'avg_speed': 0
                }
            }

        phase = int(self.state[0])
        queues = {
            'north': float(self.state[4]),
            'south': float(self.state[5]),
            'east': float(self.state[6]),
            'west': float(self.state[7])
        }
        wait_times = {
            'north': float(self.state[8]),
            'south': float(self.state[9]),
            'east': float(self.state[10]),
            'west': float(self.state[11])
        }
        occupancy = {
            'north': float(self.state[16]),
            'south': float(self.state[17]),
            'east': float(self.state[18]),
            'west': float(self.state[19])
        }

        return {
            'timestamp': int(time.time()),
            'simulation_time': int(self.simulation_time),
            'intersections': [{
                'id': 'J1',
                'phase': phase,
                'phase_name': self.get_phase_name(phase),
                'queues': queues,
                'wait_times': wait_times,
                'occupancy': occupancy
            }],
            'vehicles': [],
            'metrics': {
                'avg_travel_time': 0,
                'avg_queue_length': float(np.mean(self.state[4:8])),
                'throughput': 0,
                'total_vehicles': 0,
                'avg_speed': 0
            }
        }

    def get_phase_name(self, phase):
        phase_names = {
            0: 'NS_Straight',
            1: 'NS_LeftTurn',
            2: 'EW_Straight',
            3: 'EW_LeftTurn'
        }
        return phase_names.get(phase, 'Unknown')

    async def set_scenario(self, scenario):
        print(f"Setting scenario: {scenario}")

    async def start(self):
        async with websockets.serve(self.handle_client, self.host, self.port):
            print(f"WebSocket server started on ws://{self.host}:{self.port}")
            await asyncio.Future()


async def main():
    server = SimulationServer()
    await server.start()


if __name__ == '__main__':
    asyncio.run(main())