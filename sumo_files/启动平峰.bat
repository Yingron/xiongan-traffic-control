@echo off
chcp 65001 >nul
cd /d "%~dp0sumo_files"
sumo-gui -c "xiongan_flat.sumocfg"
