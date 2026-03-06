import logging
import time
from multiprocessing import Process
from sys import exit

from flask import Flask, request

from args import parse_args
from config_reader import RouterConfig, read_network_config
from router import Router
from cli import main as cli_main

log = logging.getLogger("werkzeug")
log.setLevel(logging.ERROR)


def create_app(cfg: RouterConfig, update_interval=1, use_cli=False, split_horizon=True, fail_protection=True, start_disabled=False):
    import sys
    import os
    import tempfile
    
    if use_cli:
        log_dir = os.path.join(tempfile.gettempdir(), "router_logs")
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "global_routers.log")
        
        sys.stdout = open(log_file, "a")
        sys.stderr = sys.stdout

    parts = cfg.address.split(":")
    if len(parts) != 2 or not parts[1].isdigit():
        raise ValueError(f"Invalid address format: {cfg.address}")
    port = int(parts[1])

    print(f"--- Iniciando Roteador {cfg.name} ---")
    print(f"Endereço: {cfg.address}")
    print(f"Rede Local: {cfg.network}")
    print(f"Vizinhos Diretos: {list(map(lambda x: x['address'], cfg.neighbors))}")

    app = Flask(cfg.name)
    router_instance = Router(cfg, update_interval, split_horizon, fail_protection)
    if start_disabled:
        router_instance.is_active = False

    @app.route("/routes", methods=["GET"])
    def get_routes():
        return router_instance.get_routes()

    @app.route("/toggle", methods=["POST"])
    def toggle():
        router_instance.is_active = not router_instance.is_active
        state = "LIGADO" if router_instance.is_active else "DESLIGADO"
        router_instance.log(f"Status alterado para {state} via API")
        return {"status": "success", "is_active": router_instance.is_active}, 200

    @app.route("/status", methods=["GET"])
    def status():
        return {"name": router_instance.name, "is_active": router_instance.is_active}, 200

    @app.route("/receive_update", methods=["POST"])
    def receive_update():
        return router_instance.receive_update(request.json)

    @app.route("/send", methods=["POST"])
    def send():
        return router_instance.send(request.json)

    app.run(host="0.0.0.0", port=port, debug=False)


if __name__ == "__main__":
    args = parse_args()
    if args.is_filled():
        router = args.to_router_config()
        create_app(router, args.interval, args.cli, args.split_horizon, args.fail_protection, args.start_disabled)
        print("Finalizando o servidor")
        exit(0)

    network = read_network_config(args.file)

    print('SPLITHORIZON', args.split_horizon)
    print('FAILPROTECTION', args.fail_protection)

    print("Iniciando os roteadores locais")
    print(f"Intervalo de Atualização: {args.interval}s")

    import tempfile
    import os
    
    log_file = os.path.join(tempfile.gettempdir(), "router_logs", "global_routers.log")
    if os.path.exists(log_file):
        os.remove(log_file)

    processes = []
    for router in network.routers:
        p = Process(target=create_app, args=(router, args.interval, args.cli, args.split_horizon, args.fail_protection, args.start_disabled))
        p.start()
        processes.append(p)

    time.sleep(1)
    
    try:
        if args.cli:
            routers_for_cli = [
                {"name": r.name, "address": r.address, "network": r.network}
                for r in network.routers
            ]
            cli_main(routers_for_cli)
        else:
            print("\nRoteadores operando em background via daemon.")
            print("Pressione Ctrl+C para encerrar todos.")
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        print("\nEncerrando a aplicação...")
    finally:
        print("Finalizando roteadores locais...")
        for p in processes:
            p.terminate()
            p.join()
