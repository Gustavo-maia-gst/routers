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
        prefix = f"[{self.name}({self.address})]"
        lines = s.split("\n")
        log_dir = os.path.join(tempfile.gettempdir(), "router_logs")
        os.makedirs(log_dir, exist_ok=True)
        with open(os.path.join(log_dir, "global_routers.log"), "a") as f:
            for line in lines:
                msg = f"{prefix} - {line}"
                print(msg)
                f.write(msg + "\n")

    def __init__(self, cfg: RouterConfig, update_interval=1, split_horizon=True, fail_protection=True):
        self.name = cfg.name
        self.address = cfg.address
        self.neighbors = cfg.neighbors
        self.my_network = cfg.network
        self.update_interval = update_interval
        self.split_horizon = split_horizon
        self.fail_protection = fail_protection
        self.is_active = True

        print(self.neighbors)

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
            
            if not self.is_active:
                continue

            self.log(
                f"[{time.ctime()}] Enviando atualizações periódicas para os vizinhos..."
            )
            try:
                self.send_updates_to_neighbors()
            except Exception as e:
                self.log(f"Erro durante a atualização periódida: {e}")

    def get_routes(self):
        """Endpoint para visualizar a tabela de roteamento atual."""
        sumarized_table = self.summarize_table()

        return jsonify(
            {
                "name": self.name,
                "is_active": self.is_active,
                "vizinhos": self.neighbors,
                "my_network": self.my_network,
                "my_address": self.address,
                "update_interval": self.update_interval,
                "routing_table": self.routing_table,  # Exibe a tabela de roteamento atual (a ser implementada)
                "summarized_table": sumarized_table,
            }
        )

    def authenticate_sender(self, sender: str):
        neighbor = next((n for n in self.neighbors if n["address"] == sender), None)
        return neighbor

    def receive_update(self, update_data):
        """Endpoint que recebe atualizações de roteamento de um vizinho."""
        if not self.is_active:
            return jsonify({"error": "Router offline"}), 503

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
        
        # Remove rotas que aprendemos deste vizinho mas que ele não anuncia mais (ex: foram sumarizadas)
        if self.fail_protection:
            routes_to_delete = []
            for net, info in self.routing_table.items():
                if info["next_hop"] == sender_address and net not in sender_table:
                    routes_to_delete.append(net)
                    
            for net in routes_to_delete:
                del self.routing_table[net]
                has_changes = True

        for net, data in sender_table.items():
            current_routing = self.routing_table.get(net)

            should_update_route = (
                # não existe essa rota ainda
                current_routing is None
                # o caminho atual passa pelo next_hop
                or current_routing["next_hop"] == sender_address
                # o custo atual é maior do que o novo caminho
                or current_routing["cost"] > cost + data["cost"]
            )

            # Se a rota vem com infinito e o sender é nosso next_hop atual, herdamos o infinito, a menos que seja para nós mesmos
            if data["cost"] == float('inf') and current_routing and current_routing["next_hop"] == sender_address and net != self.my_network:
                should_update_route = True
                
            # Só atualiza a rota se não for atingir o infinito pra sempre (evita loop). 
            # Mas permitiremos infinito explícito pra anunciar morte
            if should_update_route:
                has_changes = True
                # Propaga o infinito somando nada a ele pra não bugar float, ou soma o custo se for numérico
                new_cost = float('inf') if data["cost"] == float('inf') else cost + data["cost"]
                self.routing_table[net] = {
                    "cost": new_cost,
                    "next_hop": sender_address,
                }

        if has_changes:
            self.log("Tabela de roteamento atualizada")
            self.log(json.dumps(self.routing_table, indent=4))
        else:
            self.log("Tabela de roteamento já estava atualizada")

        return jsonify({"status": "success", "message": "Update received"}), 200

    def ip_to_int(self, ip: str) -> int:
        n = 0
        for part in ip.split("."):
            n = (n << 8) | int(part)
        return n

    def int_to_ip(self, n: int) -> str:
        return ".".join(str((n >> (8 * i)) & 0xFF) for i in reversed(range(4)))

    def can_merge(self, net1: str, net2: str):
        ip1, mask1 = net1.split("/")
        ip2, mask2 = net2.split("/")

        mask1 = int(mask1)
        mask2 = int(mask2)

        if mask1 != mask2:
            return None  # tamanhos diferentes

        base1 = self.ip_to_int(ip1)
        base2 = self.ip_to_int(ip2)

        size = 1 << (32 - mask1)

        # precisam ser consecutivos
        if abs(base1 - base2) != size:
            return None

        # bit que muda precisa ser exatamente o do prefixo
        diff = base1 ^ base2
        if diff != size:
            return None

        new_base = min(base1, base2) & ~(size)
        new_mask = mask1 - 1

        return f"{self.int_to_ip(new_base)}/{new_mask}"

    def summarize_table(self, exclude_neighbor: str = None):
        new_table = {}

        for net, info in self.routing_table.items():
            # Se o split horizon estiver ativo e o next hop for o vizinho que estamos enviando a atualização, pulamos
            if self.split_horizon and exclude_neighbor is not None and info["next_hop"] == exclude_neighbor:
                continue
            new_table[net] = info.copy()

        changed = True
        while changed:
            changed = False
            nets = list(new_table.keys())

            for i in range(len(nets)):
                for j in range(i + 1, len(nets)):
                    n1 = nets[i]
                    n2 = nets[j]

                    r1 = new_table[n1]
                    r2 = new_table[n2]

                    if self.split_horizon and r1["next_hop"] != r2["next_hop"]:
                        continue

                    merged = self.can_merge(n1, n2)
                    if merged:
                        cost = max(r1["cost"], r2["cost"])
                        hop = r1["next_hop"]

                        del new_table[n1]
                        del new_table[n2]

                        new_table[merged] = {
                            "cost": cost,
                            "next_hop": hop
                        }

                        changed = True
                        break
                if changed:
                    break

        return new_table        

    def _handle_neighbor_down(self, neighbor_address: str):
        """Seta o custo de rotas atravessando um vizinho inativo para infinito."""
        if not self.fail_protection:
            new_rounting_table = dict()
            for net, info in self.routing_table.items():
                if info["next_hop"] != neighbor_address:
                    new_rounting_table[net] = info
            self.routing_table = new_rounting_table
            return

        has_changes = False
        for net, info in self.routing_table.items():
            if info["next_hop"] == neighbor_address and info["cost"] != float('inf'):
                info["cost"] = float('inf')
                has_changes = True
        
        if has_changes:
            self.log(f"Vizinho {neighbor_address} presumido offline. Rotas ajustadas para custo infinito.")

    def send_updates_to_neighbors(self):
        for neighbor in self.neighbors:
            summarized_table = self.summarize_table(neighbor["address"])

            url = f"http://{neighbor['address']}/receive_update"

            payload = {
                "sender_address": self.address,
                "routing_table": {
                     net: {"cost": info["cost"], "next_hop": info["next_hop"]} 
                     for net, info in summarized_table.items()
                     if info["cost"] != float('inf')
                }
            }

            try:
                self.log(f"Enviando tabela para {neighbor['address']}")
                res = requests.post(url, json=payload, timeout=5)
                if res.status_code == 503:
                    raise requests.exceptions.RequestException("Serviço Indisponível (Router Offline)")
            except:
                self.log(f"Não foi possível conectar ao vizinho {neighbor}")
                self._handle_neighbor_down(neighbor["address"])


    def _find_route(self, destination: str):
         dest_ip = destination.split('/')[0] if '/' in destination else destination
         try:
             dest_int = self.ip_to_int(dest_ip)
         except Exception:
             return None, None
         
         best_match = None
         best_prefix_len = -1
         best_route = None

         for net_str, info in self.routing_table.items():
             if net_str == "localhost" or ":" in net_str:
                 continue # Ignore direct neighbor addresses in routing table
             net_ip, net_mask = net_str.split('/')
             net_mask = int(net_mask)
             try:
                 net_int = self.ip_to_int(net_ip)
             except Exception:
                 continue
             
             # Calculate subnet mask (e.g., /24 -> 0xFFFFFF00)
             mask_int = (0xFFFFFFFF << (32 - net_mask)) & 0xFFFFFFFF
             
             # Check if the destination matches the network prefix
             if (dest_int & mask_int) == (net_int & mask_int):
                 if net_mask > best_prefix_len:
                     best_prefix_len = net_mask
                     best_match = net_str
                     best_route = info

         return best_match, best_route


    def send(self, payload):
        """Recebe payload e envia para o roteador destino."""
        if not self.is_active:
            return jsonify({"error": "Router offline"}), 503

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
        
        try:
            my_net_int = self.ip_to_int(my_net_ip)
            dest_int = self.ip_to_int(dest_ip)
            mask_int = (0xFFFFFFFF << (32 - my_net_mask)) & 0xFFFFFFFF
        except Exception:
             return jsonify({"error": f"IP inválido", "trace_id": trace_id}), 400

        if (dest_int & mask_int) == (my_net_int & mask_int):
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
             res = requests.post(url, json=payload, timeout=10)
             try:
                 return jsonify(res.json()), res.status_code
             except Exception:
                 self.log(f"[TRACE_ID: {trace_id}] Resposta não-JSON do next hop {next_hop}")
                 return jsonify({"error": "Resposta inválida do next hop", "trace_id": trace_id}), 502
        except requests.exceptions.RequestException as e:
             self.log(f"[TRACE_ID: {trace_id}] Erro de conexão ao encaminhar pacote para {next_hop}: {e}")
             return jsonify({"error": "Timeout ao encaminhar pacote", "trace_id": trace_id}), 500
