from argparse import ArgumentParser
from dataclasses import dataclass

from config_reader import RouterConfig, read_neighbors


@dataclass
class Args:
    port: int
    file: str
    network: str
    interval: int
    cli: bool
    split_horizon: bool
    fail_protection: bool
    start_disabled: bool

    def is_filled(self) -> bool:
        return (
            self.port is not None and self.file is not None and self.network is not None
        )

    def to_router_config(self) -> RouterConfig:
        if not self.is_filled():
            raise ValueError("Missing required arguments")

        neighbors = read_neighbors(self.file)
        neighbors = list(map(lambda x: {"address": x[0], "cost": x[1], "network": x[0]}, neighbors))

        return RouterConfig(
            "Router A", self.network, f"127.0.0.1:{self.port}", neighbors
        )


def parse_args() -> Args:
    parser = ArgumentParser(description="Simulador de Roteador com Vetor de Distância")
    parser.add_argument(
        "--interval",
        type=int,
        default=5,
        help="Intervalo de atualização periódica em segundos.",
    )
    parser.add_argument(
        "--cli",
        action="store_true",
        help="Inicia a interface de linha de comando iterativa para depuração.",
    )
    parser.add_argument(
        "--no-split-horizon",
        action="store_false",
        dest="split_horizon",
        default=True,
        help="Desativa o mecanismo de Split Horizon (padrão é ativado).",
    )
    parser.add_argument(
        "--no-fail-protection",
        action="store_false",
        dest="fail_protection",
        default=True,
        help="Desativa mecanismos de proteção de falhas (implicit withdrawal e infinity cost).",
    )
    parser.add_argument(
        "--start-disabled",
        action="store_true",
        default=False,
        help="Inicia todos os roteadores desativados (offline). Ative-os manualmente via CLI.",
    )

    parser.add_argument(
        "-p", "--port", type=int, required=False, help="Porta para executar o roteador."
    )
    parser.add_argument(
        "-f",
        "--file",
        type=str,
        required=True,
        help="Arquivo CSV de configuração de vizinhos em simulação isolada ou configuração da rede via json em simulação distribuída.",
    )
    parser.add_argument(
        "--network",
        type=str,
        required=False,
        help="Rede administrada por este roteador (ex: 10.0.1.0/24).",
    )

    return Args(**vars(parser.parse_args()))
