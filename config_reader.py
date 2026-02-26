from dataclasses import dataclass
from typing import Any


@dataclass
class RouterConfig:
    name: str
    network: str
    address: str
    neighbors: list[dict[str, Any]]


class NetworkConfig:
    def __init__(self, routers: list[RouterConfig]):
        self.routers = routers


def get_valid_key(file: str, obj: Any, key: str):
    if key in obj:
        return obj[key]
    raise KeyError(f"Invalid format in {file}, missing key '{key}'")


def read_network_config(file: str) -> NetworkConfig:
    routers = []
    import json

    with open(file, "r") as f:
        routers_data = json.load(f)

    routers_map = {
        get_valid_key(file, router, "address"): router for router in routers_data
    }

    for router_info in routers_data:
        neighbors = read_neighbors(get_valid_key(file, router_info, "config_file"))
        routers.append(
            RouterConfig(
                name=get_valid_key(file, router_info, "name"),
                network=get_valid_key(file, router_info, "network"),
                address=get_valid_key(file, router_info, "address"),
                neighbors=[
                    {
                        "network": routers_map[n]["network"],
                        "address": routers_map[n]["address"],
                        "cost": cost,
                    }
                    for n, cost in neighbors
                ],
            )
        )
    return NetworkConfig(routers=routers)


def read_neighbors(file: str) -> list[tuple[str, int]]:
    neighbors = []
    import csv

    with open(file, "r", newline="") as f:
        reader = csv.reader(f)
        next(reader, None)
        for row in reader:
            if not row:
                continue
            neighbors.append((row[0], int(row[1])))

    return neighbors
