import os
import sys
import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List

from env.xiongan_env import XionganEnv
from training.config import ENV_CONFIG, MODEL_DIR
from stable_baselines3 import DQN, D3QN

app = FastAPI(title="Xiongan Traffic Control API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

env = None
model = None


class ActionRequest(BaseModel):
    intersection_id: str = "J1"
    phase: int = 0


class ScenarioRequest(BaseModel):
    scenario: str = "morning_peak"


class StateResponse(BaseModel):
    timestamp: int
    simulation_time: int
    intersections: List[dict]
    vehicles: List[dict]
    metrics: dict


@app.on_event("startup")
def startup():
    global env
    env_config = ENV_CONFIG.copy()
    env_config['use_gui'] = False
    env = XionganEnv(**env_config)


@app.on_event("shutdown")
def shutdown():
    if env is not None:
        env.close()


@app.post("/api/simulation/start")
async def start_simulation():
    global env
    if env is None:
        env_config = ENV_CONFIG.copy()
        env_config['use_gui'] = False
        env = XionganEnv(**env_config)
    
    state, _ = env.reset()
    return {"status": "success", "message": "Simulation started"}


@app.post("/api/simulation/stop")
async def stop_simulation():
    global env
    if env is not None:
        env.close()
        env = None
    return {"status": "success", "message": "Simulation stopped"}


@app.post("/api/simulation/reset")
async def reset_simulation():
    global env
    if env is None:
        env_config = ENV_CONFIG.copy()
        env_config['use_gui'] = False
        env = XionganEnv(**env_config)
    
    state, _ = env.reset()
    return {"status": "success", "message": "Simulation reset"}


@app.post("/api/simulation/step")
async def step_simulation(steps: int = 1):
    global env
    if env is None:
        raise HTTPException(status_code=400, detail="Simulation not started")
    
    for _ in range(steps):
        state, reward, done, _, info = env.step(0)
        if done:
            break
    
    return {"status": "success", "simulation_time": int(info.get('sim_time', 0))}


@app.post("/api/simulation/action")
async def execute_action(action_request: ActionRequest):
    global env
    if env is None:
        raise HTTPException(status_code=400, detail="Simulation not started")
    
    state, reward, done, _, info = env.step(action_request.phase)
    
    return {
        "status": "success",
        "phase": action_request.phase,
        "reward": float(reward),
        "simulation_time": int(info.get('sim_time', 0))
    }


@app.get("/api/simulation/state")
async def get_state():
    global env
    if env is None:
        raise HTTPException(status_code=400, detail="Simulation not started")
    
    state = env._get_state()
    
    return {
        "timestamp": int(time.time()),
        "simulation_time": int(env.current_step * env.delta_time),
        "intersections": [{
            "id": "J1",
            "phase": int(state[0]),
            "queues": {
                "north": float(state[4]),
                "south": float(state[5]),
                "east": float(state[6]),
                "west": float(state[7])
            },
            "wait_times": {
                "north": float(state[8]),
                "south": float(state[9]),
                "east": float(state[10]),
                "west": float(state[11])
            },
            "occupancy": {
                "north": float(state[16]),
                "south": float(state[17]),
                "east": float(state[18]),
                "west": float(state[19])
            }
        }],
        "vehicles": [],
        "metrics": {
            "avg_travel_time": 0,
            "avg_queue_length": float(sum(state[4:8]) / 4),
            "throughput": 0,
            "total_vehicles": 0,
            "avg_speed": 0
        }
    }


@app.post("/api/model/load")
async def load_model(model_type: str = "d3qn"):
    global model, env
    model_path = os.path.join(MODEL_DIR, f'{model_type}_pretrained.zip')
    
    if not os.path.exists(model_path):
        raise HTTPException(status_code=404, detail=f"Model not found: {model_path}")
    
    if env is None:
        env_config = ENV_CONFIG.copy()
        env_config['use_gui'] = False
        env = XionganEnv(**env_config)
    
    if model_type == 'd3qn':
        model = D3QN.load(model_path, env=env)
    else:
        model = DQN.load(model_path, env=env)
    
    return {"status": "success", "model": model_type}


@app.post("/api/model/predict")
async def predict_action():
    global model, env
    if model is None:
        raise HTTPException(status_code=400, detail="Model not loaded")
    if env is None:
        raise HTTPException(status_code=400, detail="Simulation not started")
    
    state, _ = env.reset()
    action, _ = model.predict(state, deterministic=True)
    
    return {"action": int(action), "phase": int(action)}


@app.post("/api/scenario/set")
async def set_scenario(scenario_request: ScenarioRequest):
    return {"status": "success", "scenario": scenario_request.scenario}


@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "env_running": env is not None}


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8000)