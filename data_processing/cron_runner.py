from data_processing.data_pre_processing import  data_ingestion_pipeline
import asyncio
import time

async def start_cron():
    while True:
        print("Running scheduled task...")
        await data_ingestion_pipeline()
        await asyncio.sleep(300)  # wait 5 minutes (300 seconds)

if __name__ == "__main__":
    asyncio.run(start_cron())