@echo off
cd /d w:\nautilusTrader\nautilus_trader_backtest
C:\Users\da\AppData\Local\Programs\Python\Python314\python.exe backtest\run_backtest.py > backtest_output.txt 2>&1
echo DONE >> backtest_output.txt