import os
import json
import requests
import subprocess
import sys
import tempfile

def get_routers():
    # Attempt to load configurations to know where routers are running
    config_path = "example_network/network.json"
    if not os.path.exists(config_path):
        print(f"Erro: {config_path} não encontrado.")
        return []

    try:
        with open(config_path) as f:
            return json.load(f)
    except Exception as e:
        print(f"Erro ao ler {config_path}: {e}")
        return []

def prompt_router(routers):
    print("\nRoteadores disponíveis:")
    for i, r in enumerate(routers):
        print(f"{i+1}. {r['name']} ({r['address']})")
    
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

def view_logs():
    log_file = os.path.join(tempfile.gettempdir(), "router_logs", "global_routers.log")
    if not os.path.exists(log_file):
        print(f"\n[!] Arquivo de log '{log_file}' não encontrado.")
        print("Talvez a rede não tenha inicializado ou gerado logs ainda.")
        return
    
    # Executa o less no arquivo para termos navegação igual ao vim
    try:
         subprocess.run(["less", log_file])
    except FileNotFoundError:
         print("Comando 'less' não encontrado no sistema. Fallback para visualização a granel:")
         with open(log_file, 'r') as f:
              print(f.read())
              
def main():
    routers = get_routers()
    if not routers:
        print("Nenhum roteador encontrado. Abortando CLI.")
        sys.exit(1)
        
    while True:
        print("\n" + "="*40)
        print("          🌐 ROUTER CLI TOOL")
        print("="*40)
        print("1. Consultar Tabela de Roteamento")
        print("2. Enviar Pacote (Send)")
        print("3. Visualizar Todos os Logs (Visão Vim)")
        print("4. Sair")
        print("="*40)
        
        choice = input("Selecione uma opção [1-4]: ")
        
        if choice == '1':
            view_routing_table(routers)
        elif choice == '2':
            send_packet(routers)
        elif choice == '3':
            view_logs()
        elif choice == '4' or choice.lower() == 'q':
            print("Encerrando CLI...")
            break
        else:
            print("Opção inválida. Tente novamente.")

if __name__ == "__main__":
    main()
