#!/bin/bash
cd /home/node/market-eyes/scripts
python3 - << PYEOF
import sys, os
sys.path.insert(0, "/home/node/market-eyes/scripts")
from dotenv import load_dotenv
load_dotenv("/home/node/market-eyes/.env")
import tushare as ts
from datetime import datetime
ts.set_token(os.getenv("TUSHARE_TOKEN"))
pro = ts.pro_api()
today = datetime.now().strftime("%Y%m%d")
df = pro.trade_cal(exchange="SSE", start_date=today, end_date=today)
if df.iloc[0]["is_open"] == 1:
    print("交易日，执行pipeline")
    os.system("python3 /home/node/market-eyes/scripts/pipeline.py --date " + datetime.now().strftime("%Y-%m-%d") + " >> /home/node/market-eyes/logs/cron.log 2>&1")
else:
    print("非交易日，跳过")
PYEOF
