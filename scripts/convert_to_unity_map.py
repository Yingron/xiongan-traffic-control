"""
将30路口SUMO路网数据转换为Unity地图JSON格式（兼容MapManager）

格式说明：
- snapshot结构包含roads, trafficLights, buildings, vehicles, targetPoints
- category值：0=targetPoint, 1=road, 2=building, 3=vehicle, 4=trafficLight
- vehicleType：0=普通车辆, 1=应急车辆
"""
import json
import re
import uuid
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
UNITY_MAP_DIR = REPO_ROOT / "frontend" / "CitySimulation" / "Assets" / "Scripts" / "Maps"

def load_junction_positions():
    """从 xiongan_30.nod.xml 读取信号路口坐标 {jid: (x, y)}"""
    nod = Path(__file__).resolve().parents[1] / "sumo_files" / "xiongan_30.nod.xml"
    text = nod.read_text(encoding="utf-8")
    return {
        m.group(1): (float(m.group(2)), float(m.group(3)))
        for m in re.finditer(r'<node id="(J\d{2})" x="([^"]+)" y="([^"]+)"', text)
    }

def generate_unity_map():
    """生成Unity地图JSON"""
    rows = 6
    cols = 5
    spacing = 200  # 路口间距200m
    # 新 30 路口路网为 6×5 网格（200m 间距），节点坐标与这里的合成网格一致：
    # x∈{0..800}，y∈{0..1000}（首行 y=1000）。用真实路口 ID 命名信号灯。
    junction_pos = load_junction_positions()
    jid_at = {pos: jid for jid, pos in junction_pos.items()}
    
    unity_map = {
        "snapshot": {
            "roads": [],
            "trafficLights": [],
            "buildings": [],
            "vehicles": [],
            "targetPoints": []
        }
    }
    
    # ============ 生成道路 ============
    # 只生成相邻路口之间的路段（与 SUMO 路网一致，共 98 条），
    # 不生成外圈之外的悬空路段。
    for row in range(rows):
        y = (rows - 1 - row) * spacing
        
        # 水平道路（东向）
        for col in range(cols - 1):
            road_id = str(uuid.uuid4())
            points = [
                {"x": col * spacing, "y": 0, "z": y},
                {"x": (col + 1) * spacing, "y": 0, "z": y}
            ]
            
            unity_map["snapshot"]["roads"].append({
                "id": road_id,
                "category": 1,
                "styleId": "section",
                "position": {"x": col * spacing + spacing/2, "y": 0, "z": y},
                "rotation": {"x": 0, "y": 0, "z": 0, "w": 1},
                "controlPoints": points,
                "width": 6,
                "speedLimit": 50
            })
        
        # 水平道路（西向）
        for col in range(cols - 1):
            road_id = str(uuid.uuid4())
            points = [
                {"x": (col + 1) * spacing, "y": 0, "z": y},
                {"x": col * spacing, "y": 0, "z": y}
            ]
            
            unity_map["snapshot"]["roads"].append({
                "id": road_id,
                "category": 1,
                "styleId": "section",
                "position": {"x": col * spacing + spacing/2, "y": 0, "z": y},
                "rotation": {"x": 0, "y": 0, "z": 0, "w": 1},
                "controlPoints": points,
                "width": 6,
                "speedLimit": 50
            })
    
    for col in range(cols):
        x = col * spacing
        
        # 垂直道路（南向）
        for row in range(rows - 1):
            road_id = str(uuid.uuid4())
            y_start = (rows - 1 - row) * spacing
            y_end = (rows - 1 - (row + 1)) * spacing
            
            points = [
                {"x": x, "y": 0, "z": y_start},
                {"x": x, "y": 0, "z": y_end}
            ]
            
            unity_map["snapshot"]["roads"].append({
                "id": road_id,
                "category": 1,
                "styleId": "section",
                "position": {"x": x, "y": 0, "z": y_start - spacing/2},
                "rotation": {"x": 0, "y": 0, "z": 0, "w": 1},
                "controlPoints": points,
                "width": 6,
                "speedLimit": 50
            })
        
        # 垂直道路（北向）
        for row in range(rows - 1):
            road_id = str(uuid.uuid4())
            y_start = (rows - 1 - row) * spacing
            y_end = (rows - 1 - (row + 1)) * spacing
            
            points = [
                {"x": x, "y": 0, "z": y_end},
                {"x": x, "y": 0, "z": y_start}
            ]
            
            unity_map["snapshot"]["roads"].append({
                "id": road_id,
                "category": 1,
                "styleId": "section",
                "position": {"x": x, "y": 0, "z": y_start - spacing/2},
                "rotation": {"x": 0, "y": 0, "z": 0, "w": 1},
                "controlPoints": points,
                "width": 6,
                "speedLimit": 50
            })
    
    # ============ 生成信号灯 ============
    road_list = unity_map["snapshot"]["roads"]
    for row in range(rows):
        for col in range(cols):
            x = col * spacing
            y = (rows - 1 - row) * spacing
            
            # 找到控制的道路
            controlled_roads = []
            for road in road_list:
                points = road["controlPoints"]
                # 检查道路是否经过这个路口
                for p in points:
                    if abs(p["x"] - x) < spacing/2 and abs(p["z"] - y) < spacing/2:
                        controlled_roads.append(road["id"])
                        break
                if len(controlled_roads) >= 2:
                    break
            
            tl_id = jid_at.get((x, y), f"J{(row*cols + col + 1):02d}")
            
            unity_map["snapshot"]["trafficLights"].append({
                "id": tl_id,
                "category": 4,
                "styleId": "Empty_TrafficLight",
                "position": {"x": x, "y": 5, "z": y},
                "rotation": {"x": 0, "y": 0, "z": 0, "w": 1},
                "controlledRoadIds": controlled_roads[:2],
                "currentGreenRoadId": controlled_roads[0] if controlled_roads else "",
                "timeInPhase": 0
            })
    
    # ============ 生成建筑 ============
    # 建筑只放在相邻道路围成的内部街区中心，不占用道路或路口。静态地图不再
    # 预置车辆，所有车辆由 SUMO 通过 WebSocket 动态生成，避免与其重叠。
    building_styles = ("Sky_big_color01", "Fast_Food_color01")
    for row in range(rows - 1):
        for col in range(cols - 1):
            unity_map["snapshot"]["buildings"].append({
                "id": f"B{row + 1:02d}{col + 1:02d}",
                "category": 2,
                "styleId": building_styles[(row + col) % len(building_styles)],
                "position": {
                    "x": (col + 0.5) * spacing,
                    "y": 0,
                    "z": (row + 0.5) * spacing,
                },
                "rotation": {"x": 0, "y": 0, "z": 0, "w": 1},
                # 零尺寸表示保留预制体自身比例，避免以 JSON 覆盖模型缩放。
                "size": {"x": 0, "y": 0, "z": 0},
            })

    # ============ 生成目标点 ============
    target_point_id = str(uuid.uuid4())
    unity_map["snapshot"]["targetPoints"].append({
        "id": target_point_id,
        "category": 0,
        "styleId": "red_sphere",
        "position": {"x": 400, "y": 0, "z": 300},
        "rotation": {"x": 0, "y": 0, "z": 0, "w": 1}
    })
    
    print(f"生成统计：道路={len(road_list)}, 信号灯={len(unity_map['snapshot']['trafficLights'])}, "
          f"建筑={len(unity_map['snapshot']['buildings'])}, 静态车辆=0, 目标点=1")
    
    return unity_map

def write_unity_map(unity_map):
    """将30路口地图写入仓库唯一的 frontend Unity工程。"""
    if not UNITY_MAP_DIR.parent.parent.parent.parent.exists():
        raise FileNotFoundError("未找到 frontend/CitySimulation Unity工程")
    UNITY_MAP_DIR.mkdir(parents=True, exist_ok=True)
    output_path = UNITY_MAP_DIR / "xiongan_30.json"
    output_path.write_text(
        json.dumps(unity_map, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"[OK] Unity地图文件已生成: {output_path}")
    return output_path


def main():
    # 生成Unity地图
    unity_map = generate_unity_map()
    
    output_path = write_unity_map(unity_map)
    print(f"\n[OK] Unity地图文件已生成: {output_path}")
    
    # 在Unity中加载方法：
    print("\n在Unity中加载地图：")
    print("   1. 进入Play模式")
    print("   2. 在右侧面板输入地图名: xiongan_30")
    print("   3. 点击 loadMap")

if __name__ == '__main__':
    main()
