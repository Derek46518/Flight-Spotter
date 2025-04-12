import os
import re
import json
import time
import gzip
#import random
import shutil
import requests
from tqdm import tqdm
from datetime import datetime, timedelta

# data description at: https://www.adsbexchange.com/products/historical-data/
ADSB_EX_HISTORICAL_DATA_URL = "https://samples.adsbexchange.com"
# set data you want to download here
ENABLES_DATA = ["readsb-hist", "traces"] #, "hires-traces", "acas", "operations"
# set time you want to download here
ENABLES_YEAR = ["2025"]#["2016", "2017", "2018", "2019", "2020", "2021", "2022", "2023", "2024", "2025"]
ENABLES_MONTH = ["04"]#["01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12"]
ENABLES_DATE = ["01"] # free data only january available, so don't change this one

# get response buy url, download file, unzip is optional
def download_json_gz(path:str, url:str, filename:str, description:str, unzip:bool = False):
    # get response
    response = requests.get(url, stream = True)
    if response.ok:
        size = int(response.headers.get("content-length", 0))
        # download .gz file
        with open(f"{path}./{filename}", "wb") as f:
            with tqdm.wrapattr(response.raw, "read", total = size, unit = "B", unit_scale = True, desc = description) as r:
                shutil.copyfileobj(r, f)
        # don't unzip here cuz too big, just unzip when need
        if unzip and filename.endswith(".json.gz"):
            # unzip and save
            with gzip.open(f"{path}./{filename}", "rb") as f_in:
                with open(f"{path}./{filename[:-3]}", "wb") as f_out: # remove ".gz"
                    shutil.copyfileobj(f_in, f_out)
            # delete .gz file
            if os.path.exists(f"{path}./{filename}"):
                os.remove(f"{path}./{filename}")
    else:
        print(f"Failed: {description}")

# Aircraft database (updated daily from government and various sources): http://downloads.adsbexchange.com/downloads/basic-ac-db.json.gz
# Please note that all files are in gzip compressed format. “traces” and “hires-traces” are in gzip format, but do not have the .gz extension.
# Your web browser may uncompress and display the raw JSON files based on the headers, but any programmatic access should anticipate gzipped JSON.
def update_basic_aircraft_database(path:str):
    # delete old data
    if os.path.exists(f"{path}./basic-ac-db.json.gz"):
        os.remove(f"{path}./basic-ac-db.json.gz")
    if os.path.exists(f"{path}./basic-ac-db.json"):
        os.remove(f"{path}./basic-ac-db.json")
    # download
    download_json_gz(path = path, url = "http://downloads.adsbexchange.com/downloads/basic-ac-db.json.gz", filename = "basic-ac-db.json.gz", description = "Updating aircraft database")

# “readsb-hist” – Snapshots of all global airborne traffic are archived every 5 seconds starting April 2020, (prior data is available every 60 secs from starting in July 2016).
def get_readsb_hist(path:str):
    # get start and end date
    for year in ENABLES_YEAR:
        for month in ENABLES_MONTH:
            for date in ENABLES_DATE:
                # judge rate
                if int(year) < 2020 or (int(year) <= 2020 and int(month) <= 3): # rate: data per 60 seconds
                    rate = 60
                else: # rate: data per 5 seconds
                    rate = 5
                
                # download
                cur_time = datetime.strptime("000000", "%H%M%S")
                end_time = datetime.strptime("235959", "%H%M%S")
                while cur_time < end_time:
                    filename = cur_time.strftime("%H%M%SZ.json.gz") # 000000Z.json.gz
                    store_name = f"{year}_{month}_{date}_{filename[:-9]}.json.gz" # 2025_04_01_000000.json.gz
                    # check if .json.gz file exists
                    if os.path.exists(f"{path}./{store_name}"):
                        cur_time += timedelta(seconds = rate)
                        continue
                    # download
                    download_json_gz(path = path, url = f"{ADSB_EX_HISTORICAL_DATA_URL}/readsb-hist/{year}/{month}/{date}/{filename}", filename = store_name, description = f"Downloading {store_name}", unzip = True)
                    # update time
                    cur_time += timedelta(seconds = rate)

                    # avoid Anti-DDoS
                    time.sleep(1) # random.randint(1, 5)) # 1-5 seconds

# “Trace Files” – Activity by individual ICAO hex for all aircraft during one 24-hour period are sub-organized by last two digits of hex code.
# “hires-traces” – Same as trace files, but with an even higher sample rate of 2x per second, for detailed analysis of flightpaths, accidents, etc.
def get_traces(path:str, hires:bool = False):
    res = "hires-traces" if hires else "traces"
    # get start and end date
    for year in ENABLES_YEAR:
        for month in ENABLES_MONTH:
            for date in ENABLES_DATE:
                # get the indices form html
                file_index = requests.get(f"{ADSB_EX_HISTORICAL_DATA_URL}/{res}/{year}/{month}/{date}/index.json", stream = True).json()
                # build table
                table = {}
                for icao_hex in tqdm(file_index["traces"], desc = f"Building index for {res}/{year}-{month}-{date}"):
                    icao_code = icao_hex.replace("trace_full_", "").replace(".json", "")
                    if bool(re.match(r'^[0-9a-fA-F]{6}$', icao_code)):
                        # build hash table
                        # use icao last 2 hex as key
                        # table = {
                        #     "97": ["008597", "008697", "00b097", ... 
                        # }
                        if icao_code[-2:] not in table:
                            table[icao_code[-2:]] = []
                        table[icao_code[-2:]].append(icao_hex)
                    else:
                        continue
                        # filename is in the format of f"trace_full_{icao_code}.json"
                        # hex: the 24-bit ICAO identifier of the aircraft, as 6 hex digits.
                        # The identifier may start with '~', this means that the address is a non-ICAO address (e.g. from TIS-B).
                        # so if "~" in filename, skip
                        # ex. "trace_full_e80600.json" -> normal
                        # ex. "trace_full_~268400.json" -> non-ICAO
                # sort
                table = dict(sorted(table.items())) # sort key
                for key in table: # sort value
                    table[key] = sorted(table[key])
                # download
                for last_2_hex in table:
                    for icao_hex in tqdm(table[last_2_hex], desc = f"Downloading files that last 2 hex is {last_2_hex}"):
                        json_file = requests.get(f"{ADSB_EX_HISTORICAL_DATA_URL}/{res}/{year}/{month}/{date}/{last_2_hex}/trace_full_{icao_hex}.json", stream = True)
                        if json_file.ok:
                            jf = json_file.json()
                            with open(f"{path}./{year}_{month}_{date}_{icao_hex}.json", "w") as f:
                                json.dump(jf, f, indent = 4)
                        time.sleep(1)

# “ACAS” – TCAS/ACAS alerts detected by our ground stations, by day.
def get_acas(path:str):
    pass

# “operations” – Using ADS-B path data, we determine takeoffs and landings (with runway used) at airports and heliports worldwide.
def get_operations(path:str):
    pass

# main
def get_data():
    # define path
    basic_aircraft_path = "./data./aircraft"
    adsbex_path = "./data./historical_adsbex_sample"
    # create data folder
    os.makedirs("./data", exist_ok = True)
    os.makedirs(basic_aircraft_path, exist_ok = True)
    os.makedirs(adsbex_path, exist_ok = True)

    # daily check for new data
    if not os.path.exists(f"{basic_aircraft_path}./basic-ac-db.json"): # or check_by_daily_time
        update_basic_aircraft_database(basic_aircraft_path)
    
    # download historical data
    for enable in ENABLES_DATA:
        os.makedirs(f"{adsbex_path}./{enable}", exist_ok=True)
        match enable:
            case "readsb-hist":
                get_readsb_hist(f"{adsbex_path}./readsb-hist")
            case "traces":
                get_traces(f"{adsbex_path}./traces")
            case "hires-traces":
                get_traces(f"{adsbex_path}./hires-traces", hires = True)
            case "acas":
                get_acas(f"{adsbex_path}./acas")
            case "operations":
                get_operations(f"{adsbex_path}./operations")
            case _:
                raise ValueError(f"Error: {enable} not available.")

if __name__ == "__main__":
    get_data()