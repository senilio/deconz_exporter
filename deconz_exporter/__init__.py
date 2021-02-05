import argparse
from os import makedirs, path
from sys import stderr
from time import sleep
from typing import Any, Dict, Generator
from wsgiref.simple_server import make_server

import requests
from prometheus_client import make_wsgi_app
from prometheus_client.core import REGISTRY, GaugeMetricFamily, Metric

from .device import Device, device_from_dict


class DeconzCollector:
    def __init__(self, device: Device, api_key: str):
        self.device = device
        self.api_path = f"http://{device.internalipaddress}:{device.internalport}/api"
        self.api_key = api_key

    def collect(self) -> Generator[Metric, None, None]:
        temperature = GaugeMetricFamily(
            "deconz_temperature_celsius",
            "deCONZ temperature sensor data",
            labels=["uid", "name", "manufacturer", "model"],
        )

        humidity = GaugeMetricFamily(
            "deconz_humidity_percent", 
            "deCONZ humidity sensor data", 
            labels=["uid", "name", "manufacturer", "model"]
        )

        pressure = GaugeMetricFamily(
            "deconz_pressure_pascal", 
            "deCONZ pressure sensor data", 
            labels=["uid", "name", "manufacturer", "model"]
        )

        power = GaugeMetricFamily(
            "deconz_power_watt", 
            "deCONZ momentary power", 
            labels=["uid", "name", "manufacturer", "model"]
        )

        consumption = GaugeMetricFamily(
            "deconz_power_kWh", 
            "deCONZ power consumption", 
            labels=["uid", "name", "manufacturer", "model"]
        )

        for sensor in requests.get(f"{self.api_path}/{self.api_key}/sensors").json().values():
            print(sensor)
            if sensor["type"] == "ZHATemperature":
                temperature.add_metric(
                    [
                        sensor["uniqueid"],
                        sensor["name"], 
                        sensor["manufacturername"],
                        sensor["modelid"]
                    ], 
                    sensor["state"]["temperature"] / 100
                )
            elif sensor["type"] == "ZHAHumidity":
                humidity.add_metric(
                    [
                        sensor["uniqueid"],
                        sensor["name"],
                        sensor["manufacturername"],
                        sensor["modelid"]
                    ], 
                    sensor["state"]["humidity"] / 100
                )
            elif sensor["type"] == "ZHAPressure":
                pressure.add_metric(
                    [
                        sensor["uniqueid"],
                        sensor["name"], 
                        sensor["manufacturername"],
                        sensor["modelid"]
                    ], 
                    sensor["state"]["pressure"] * 100
                )
            elif sensor["type"] == "ZHAPower":
                power.add_metric(
                    [
                        sensor["uniqueid"],
                        sensor["name"], 
                        sensor["manufacturername"],
                        sensor["modelid"]
                    ], 
                    sensor["state"]["power"]
                )
            elif sensor["type"] == "ZHAConsumption":
                consumption.add_metric(
                    [
                        sensor["uniqueid"],
                        sensor["name"], 
                        sensor["manufacturername"],
                        sensor["modelid"]
                    ], 
                    sensor["state"]["consumption"] / 1000
                )

        yield temperature
        yield humidity
        yield pressure
        yield power
        yield consumption


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api_key_directory", default="api_keys")
    parser.add_argument("--listen_host", default="")
    parser.add_argument("--listen_port", default=9759)
    args = parser.parse_args()
    makedirs(args.api_key_directory, exist_ok=True)
    for device_dict in requests.get("https://dresden-light.appspot.com/discover").json():
        device = device_from_dict(device_dict)
        api_path = f"http://{device.internalipaddress}:{device.internalport}/api"
        makedirs(args.api_key_directory, exist_ok=True)
        api_key_file = path.join(args.api_key_directory, device.id)
        if path.isfile(api_key_file):
            with open(api_key_file) as f:
                api_key = f.read()
        else:
            unlocked = False
            while not unlocked:
                response = requests.post(api_path, json={"devicetype": "deconz_exporter"})
                if response.status_code != 403:
                    response.raise_for_status()
                if response.status_code == 200:
                    unlocked = True
                else:
                    print(f"{device.id}: {response.json()[0]['error']['description']}", file=stderr)
                    sleep(10)
            api_key = response.json()[0]["success"]["username"]
            with open(api_key_file, "w") as f:
                f.write(api_key)
        REGISTRY.register(DeconzCollector(device, api_key))
    app = make_wsgi_app()
    httpd = make_server(args.listen_host, args.listen_port, app)
    httpd.serve_forever()

if __name__ == "__main__":
    main()
