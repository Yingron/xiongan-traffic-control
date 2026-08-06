@echo off
chcp 65001 >nul
cd /d "%~dp0"
sumo-gui -c "xiongan_morning.sumocfg" --start
