import json
import os
import tempfile
import threading
import time
import uuid

import requests
from flask import jsonify, request

from config_reader import RouterConfig


class Router:
    def log(self, s: str):
        msg = f"[{self.name}({self.address})] - {s}"
        print(msg)
        log_dir = os.path.join(tempfile.gettempdir(), "router_logs")
        os.makedirs(log_dir, exist_ok=True)
        with open(os.path.join(log_dir, "global_routers.log"), "a") as f:
            f.write(msg + "\n")

    def __init__(self, cfg: RouterConfig, update_interval=1):
        self.name = cfg.name
        self.address = cfg.address
        self.neighbors = cfg.neighbors
        self.my_network = cfg.network
        self.update_interval = update_interval

        self.routing_table = {}
        self.routing_table[self.my_network] = {"cost": 0, "next_hop": self.address}
        for n in cfg.neighbors:
            self.routing_table[n["network"]] = {
                "cost": n["cost"],
                "next_hop": n["address"],
            }

        self.log("Tabela de roteamento inicial router")
        self.log(json.dumps(self.routing_table, indent=4))

        # Inicia o processo de atualização periódica em uma thread separada
        self._start_periodic_updates()

    def _start_periodic_updates(self):
        """Inicia uma thread para enviar atualizações periodicamente."""
        thread = threading.Thread(target=self._periodic_update_loop)
        thread.daemon = True
        thread.start()

    def _periodic_update_loop(self):
        """Loop que envia atualizações de roteamento em intervalos regulares."""
        while True:
            time.sleep(self.update_interval)
            self.log(
                f"[{time.ctime()}] Enviando atualizações periódicas para os vizinhos..."
            )
            try:
                self.send_updates_to_neighbors()
            except Exception as e:
                self.log(f"Erro durante a atualização periódida: {e}")

    def get_routes(self):
        """Endpoint para visualizar a tabela de roteamento atual."""
        return jsonify(
            {
                "name": self.name,
                "vizinhos": self.neighbors,
                "my_network": self.my_network,
                "my_address": self.address,
                "update_interval": self.update_interval,
                "routing_table": self.routing_table,  # Exibe a tabela de roteamento atual (a ser implementada)
            }
        )

    def authenticate_sender(self, sender: str):
        neighbor = next((n for n in self.neighbors if n["address"] == sender), None)
        return neighbor

    def receive_update(self, update_data):
        """Endpoint que recebe atualizações de roteamento de um vizinho."""
        if not update_data:
            return jsonify({"error": "Invalid request"}), 400

        update_data = request.json
        sender_address = update_data.get("sender_address")
        sender_table = update_data.get("routing_table")

        if not sender_address or not isinstance(sender_table, dict):
            return jsonify({"error": "Faltando sender_address ou routing_table"}), 400

        self.log(f"Recebida atualização de {sender_address}:")
        self.log(json.dumps(sender_table, indent=4))

        neighbor = self.authenticate_sender(sender_address)
        if not neighbor:
            self.log(f"Rejeitando atualização de router não confiável {sender_address}")
            return jsonify({"error": "Sender não autorizado"}), 401

        cost = neighbor["cost"]
        has_changes = False
        for net, data in sender_table.items():
            current_routing = self.routing_table.get(net)

            should_update_route = (
                # não existe essa rota ainda
                current_routing is None
                or (
                    # existe indo para o sender porém o cost mudou
                    current_routing["next_hop"] == sender_address
                    and current_routing["cost"] != cost + data["cost"]
                )
                # o custo atual é maior do que o novo caminho
                or current_routing["cost"] > cost + data["cost"]
            )

            if should_update_route:
                has_changes = True
                self.routing_table[net] = {
                    "cost": cost + data["cost"],
                    "next_hop": sender_address,
                }

        if has_changes:
            self.log("Tabela de roteamento atualizada")
            self.log(json.dumps(self.routing_table, indent=4))
        else:
            self.log("Tabela de roteamento já estava atualizada")

        return jsonify({"status": "success", "message": "Update received"}), 200

    def make_table_for(self, neighbor):
        table = {}
        for net, info in self.routing_table.items():
            if info["next_hop"] != neighbor:
                table[net] = {"cost": info["cost"]}
            else:
                table[net] = {
                    "cost": float("inf"),
                }
        return table

    def _ip_to_bin(self, ip: str) -> str:
        parts = ip.split('.')
        return ''.join([f"{int(p):08b}" for p in parts])

    def _bin_to_ip(self, b: str) -> str:
        parts = [str(int(b[i:i+8], 2)) for i in range(0, 32, 8)]
        return '.'.join(parts)
        
    def _summarize_routes(self):
        """Resume rotas agrupando sub-redes encontrando o prefixo comum iterativamente."""
        routes_by_next_hop = {}
        for net_str, info in self.routing_table.items():
            cost = info["cost"]
            next_hop = info["next_hop"]

            if next_hop not in routes_by_next_hop:
                routes_by_next_hop[next_hop] = {}
            if cost not in routes_by_next_hop[next_hop]:
                routes_by_next_hop[next_hop][cost] = []

            # net_str is like "10.0.1.0/24"
            ip_str, mask_str = net_str.split('/')
            bin_ip = self._ip_to_bin(ip_str)
            mask = int(mask_str)
            routes_by_next_hop[next_hop][cost].append((bin_ip, mask))

        new_table = {}
        for next_hop, costs in routes_by_next_hop.items():
            for cost, networks in costs.items():
                if not networks:
                    continue
                
                merged = True
                while merged:
                    merged = False
                    networks.sort() # Sort by binary IP
                    
                    next_networks = []
                    skip_next = False
                    
                    i = 0
                    while i < len(networks):
                        if i < len(networks) - 1:
                            net1, mask1 = networks[i]
                            net2, mask2 = networks[i+1]
                            
                            # Can only merge if masks are equal
                            if mask1 == mask2:
                                bit_idx = mask1 - 1
                                if net1[:bit_idx] == net2[:bit_idx] and net1[bit_idx] == '0' and net2[bit_idx] == '1':
                                    # Merge successful
                                    next_networks.append((net1, mask1 - 1))
                                    merged = True
                                    i += 2
                                    continue
                        
                        next_networks.append(networks[i])
                        i += 1
                        
                    networks = next_networks
                
                # Add all resulting summarized networks to the table
                for bin_ip, mask in networks:
                    # Ensure bits after mask are zero
                    masked_bin_ip = bin_ip[:mask].ljust(32, '0')
                    summarized_ip = self._bin_to_ip(masked_bin_ip)
                    new_table[f"{summarized_ip}/{mask}"] = {"cost": cost, "next_hop": next_hop}
        
        return new_table

    def send_updates_to_neighbors(self):
        summarized_table = self._summarize_routes()
        for neighbor in self.neighbors:
            url = f"http://{neighbor['address']}/receive_update"

            payload = {
                "sender_address": self.address,
                # We need to adapt make_table_for to work with the summarized table 
                # or just use the summarized table if make_table_for is no longer needed
                # For split horizon we need to filter out routes learned from this neighbor
                "routing_table": {
                     net: {"cost": info["cost"]} 
                     for net, info in summarized_table.items() 
                     if info["next_hop"] != neighbor["address"]
                }
            }

            try:
                self.log(f"Enviando tabela para {neighbor['address']}")
                requests.post(url, json=payload, timeout=5)
            except requests.exceptions.RequestException as e:
                self.log(f"Não foi possível conectar ao vizinho {neighbor}. Erro: {e}")

    def _find_route(self, destination: str):
         dest_ip = destination.split('/')[0] if '/' in destination else destination
         dest_bin = self._ip_to_bin(dest_ip)
         
         best_match = None
         best_prefix_len = -1
         best_route = None

         for net_str, info in self.routing_table.items():
             net_ip, net_mask = net_str.split('/')
             net_mask = int(net_mask)
             net_bin = self._ip_to_bin(net_ip)
             
             # Check if the destination matches the network prefix
             if dest_bin[:net_mask] == net_bin[:net_mask]:
                 if net_mask > best_prefix_len:
                     best_prefix_len = net_mask
                     best_match = net_str
                     best_route = info

         return best_match, best_route


    def send(self, payload):
        """Recebe payload e envia para o roteador destino."""
        if not payload:
            return jsonify({"error": "Invalid request"}), 400
        
        source = payload.get("source")
        destination = payload.get("destination")
        message = payload.get("payload")
        
        # Inject trace ID if it doesn't exist
        trace_id = payload.get("trace_id")
        if not trace_id:
            trace_id = str(uuid.uuid4())
            payload["trace_id"] = trace_id

        if not source or not destination or not message:
            return jsonify({"error": "Faltando source, destination ou payload"}), 400

        self.log(f"[TRACE_ID: {trace_id}] Recebido pacote originado em {source} destinado a {destination}. Conteúdo: {message}")

        # Check if it reached the final router's subnetwork
        my_net_ip, my_net_mask = self.my_network.split('/')
        my_net_mask = int(my_net_mask)
        
        dest_ip = destination.split('/')[0] if '/' in destination else destination
        
        my_net_bin = self._ip_to_bin(my_net_ip)
        dest_bin = self._ip_to_bin(dest_ip)

        if dest_bin[:my_net_mask] == my_net_bin[:my_net_mask]:
             self.log(f"[TRACE_ID: {trace_id}] Pacote alcançou a rede destino local: {message}")
             return jsonify({
                 "status": "success", 
                 "message": "Pacote entregue no destino final",
                 "trace_id": trace_id
             }), 200

        # Find the best route
        match, route = self._find_route(destination)

        if not route:
             self.log(f"[TRACE_ID: {trace_id}] Descarte! Sem rota para host {destination}")
             return jsonify({"error": f"Sem rota para destino {destination}", "trace_id": trace_id}), 404

        next_hop = route["next_hop"]

        # Encaminha o pacote para o next hop
        url = f"http://{next_hop}/send"
        self.log(f"[TRACE_ID: {trace_id}] Encaminhando pacote via Next Hop {next_hop}")
        try:
             res = requests.post(url, json=payload, timeout=5)
             return jsonify(res.json()), res.status_code
        except requests.exceptions.RequestException as e:
             self.log(f"[TRACE_ID: {trace_id}] Erro de conexão ao encaminhar pacote para {next_hop}: {e}")
             return jsonify({"error": "Timeout ao encaminhar pacote", "trace_id": trace_id}), 500
