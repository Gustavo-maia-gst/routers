import os
import json
import requests
import subprocess
import sys
import tempfile

# ANSI color codes
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"
BOLD = "\033[1m"

def get_router_status(address):
    """Consulta o endpoint /status para verificar se o roteador está ativo."""
    try:
        res = requests.get(f"http://{address}/status", timeout=2)
        if res.status_code == 200:
            data = res.json()
            return data.get("is_active", False)
    except requests.exceptions.RequestException:
        pass
    return None  # Unreachable

def print_router_list(routers):
    """Exibe a lista de roteadores com status colorido."""
    for i, r in enumerate(routers):
        status = get_router_status(r['address'])
        if status is None:
            tag = f"{RED}UNREACHABLE{RESET}"
        elif status:
            tag = f"{GREEN}ON{RESET}"
        else:
            tag = f"{RED}OFF{RESET}"
        print(f"  {i+1}. {r['name']} ({r['address']}) - {r['network']} [{tag}]")

def prompt_router(routers):
    choice = input("\nEscolha um roteador (número) ou 'c' para cancelar: ")
    if choice.lower() == 'c':
        return None
        
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(routers):
            return routers[idx]
    except Exception:
        pass
    
    print("Opção inválida.")
    return None

def view_routing_table(routers):
    r = prompt_router(routers)
    if not r: return
    
    try:
        res = requests.get(f"http://{r['address']}/routes")
        if res.status_code != 200:
             print(f"Erro ao consultar roteador. Status: {res.status_code}")
             return
             
        data = res.json()
        print(f"\n--- Tabela de Roteamento: {r['name']} ({r['network']}) ---")
        print(f"{'Destino/Rede':<20} | {'Next Hop':<20} | {'Custo':<5}")
        print("-" * 50)
        
        routing_table = data.get("routing_table", {})
        if not routing_table:
             print("Tabela vazia ou indisponível.")
             
        for net, info in routing_table.items():
            print(f"{net:<20} | {info['next_hop']:<20} | {info['cost']:<5}")
            
        print("-" * 50)

        summarized_table = data.get("summarized_table", {})
        if summarized_table:
            print(f"\n--- Tabela Sumarizada (A ser Anunciada) ---")
            print(f"{'Destino/Rede':<20} | {'Next Hop':<20} | {'Custo':<5}")
            print("-" * 50)
            for net, info in summarized_table.items():
                print(f"{net:<20} | {info['next_hop']:<20} | {info['cost']:<5}")
            print("-" * 50)
    except requests.exceptions.RequestException as e:
        print(f"Erro de conexão ao consultar roteador: {e}")

def send_packet(routers):
    r = prompt_router(routers)
    if not r: return
    
    dest = input("Digite o IP ou Rede de destino (ex: 10.0.5.10): ")
    if not dest: return
    
    payload = input("Digite a mensagem/payload: ")
    
    try:
        url = f"http://{r['address']}/send"
        payload_data = {
            "source": r['address'],
            "destination": dest,
            "payload": payload
        }
        res = requests.post(url, json=payload_data, timeout=5)
        response_json = res.json()
        trace_id = response_json.get("trace_id", "DESCONHECIDO")
        
        if res.status_code == 200:
            print(f"\n[+] Sucesso! TRACE_ID: {trace_id}")
            print(f"Resposta: {response_json}")
        else:
            print(f"\n[-] Falha ao enviar! TRACE_ID: {trace_id}")
            print(f"Erro: {response_json}")
            
        # Trazendo o trace interativo para dentro do send
        import time
        time.sleep(0.5) # Tempo rápido para garantir as escritas nos logs
        trace_packet(trace_id)
            
    except requests.exceptions.RequestException as e:
        print(f"Erro ao enviar pacote: {e}")

def trace_packet(trace_id):
    log_file = os.path.join(tempfile.gettempdir(), "router_logs", "global_routers.log")
    if not os.path.exists(log_file):
        return

    print(f"\n--- Rastreamento de Rota (TRACE_ID: {trace_id}) ---")
    found = False
    with open(log_file, 'r') as f:
        for line in f:
            if f"[TRACE_ID: {trace_id}]" in line:
                print(line.strip())
                found = True
                
    if not found:
        print("Nenhum registro encontrado para esse pacote nos logs.")
    print("-" * 60)

def toggle_router(routers):
    r = prompt_router(routers)
    if not r: return
    
    try:
        url = f"http://{r['address']}/toggle"
        res = requests.post(url, timeout=5)
        if res.status_code == 200:
            data = res.json()
            estado = "ON" if data["is_active"] else "OFF"
            print(f"\n[+] Roteador {r['name']} alternado para: {estado}")
        else:
             print(f"\n[-] Falha ao alternar status do roteador. HTTP {res.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"Erro de conexão ao acessar o roteador: {e}")

def view_logs(routers):
    log_file = os.path.join(tempfile.gettempdir(), "router_logs", "global_routers.log")
    if not os.path.exists(log_file):
        print(f"\n[!] Arquivo de log '{log_file}' não encontrado.")
        print("Talvez a rede não tenha inicializado ou gerado logs ainda.")
        return
    
    choice = input("Filtrar por roteador? (número ou Enter para todos): ").strip()
    
    filter_name = None
    if choice:
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(routers):
                filter_name = routers[idx]['name']
            else:
                print("Número inválido. Mostrando todos.")
        except ValueError:
            print("Entrada inválida. Mostrando todos.")

    if filter_name:
        # Filtra as linhas e abre com less via pipe
        with open(log_file, 'r') as f:
            filtered = [line for line in f if f"[{filter_name}(" in line]
        
        if not filtered:
            print(f"Nenhum log encontrado para {filter_name}.")
            return
        
        # Escreve num arquivo temporário e abre com less
        tmp_filtered = os.path.join(tempfile.gettempdir(), "router_logs", "filtered.log")
        with open(tmp_filtered, 'w') as f:
            f.writelines(filtered)
        try:
            subprocess.run(["less", tmp_filtered])
        except FileNotFoundError:
            print("".join(filtered))
    else:
        try:
            subprocess.run(["less", log_file])
        except FileNotFoundError:
            print("Comando 'less' não encontrado no sistema. Fallback:")
            with open(log_file, 'r') as f:
                print(f.read())
              
def main(routers):
    if not routers:
        print("Nenhum roteador encontrado. Abortando CLI.")
        sys.exit(1)
        
    while True:
        print("\n" + "="*50)
        print("            ROUTER CLI TOOL")
        print("="*50)
        print_router_list(routers)
        print("-"*50)
        print("  A. Consultar Tabela de Roteamento")
        print("  B. Enviar Pacote (Send)")
        print("  C. Visualizar Todos os Logs")
        print("  D. Ligar/Desligar Roteador (Simular Queda)")
        print("  Q. Sair")
        print("="*50)
        
        choice = input("Selecione uma opção: ").strip().lower()
        
        if choice == 'a' or choice == '1':
            view_routing_table(routers)
            input("\nPressione Enter para voltar ao menu...")
        elif choice == 'b' or choice == '2':
            send_packet(routers)
            input("\nPressione Enter para voltar ao menu...")
        elif choice == 'c' or choice == '3':
            view_logs(routers)
        elif choice == 'd' or choice == '4':
            toggle_router(routers)
            input("\nPressione Enter para voltar ao menu...")
        elif choice == 'q' or choice == '5':
            print("Encerrando CLI...")
            break
        else:
            print("Opção inválida. Tente novamente.")

if __name__ == "__main__":
    main()
