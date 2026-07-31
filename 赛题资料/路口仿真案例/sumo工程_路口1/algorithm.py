# 相关包导入
import random
import os
import sys
import optparse
import traci
from sumolib import checkBinary
import pandas as pd



# SUMO环境变量配置，需根据用户的实际配置进行调整
if 'SUMO_HOME' in os.environ:
    tools = os.path.join(os.environ['SUMO_HOME'], 'tools')
    sys.path.append(tools)
else:
    sys.exit("please declare environment variable 'SUMO_HOME'")

def get_options():
    optParser = optparse.OptionParser()
    optParser.add_option("--nogui", action="store_true",
                         default=False, help="run the commandline version of sumo")
    options, args = optParser.parse_args()
    return options


if __name__ == '__main__' :
    options = get_options()
    if options.nogui:
        sumoBinary = checkBinary('sumo')
    else:
        sumoBinary = checkBinary('sumo-gui')
    # 启动工程文件
    traci.start([sumoBinary, "-c", "demo_1.sumocfg"])  # ,"--start"



    for step in range(3600):


        #####   请在此编写算法   ####


        traci.simulationStep()
    traci.close()