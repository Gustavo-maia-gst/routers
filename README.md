# Simulador de Roteamento (Distance Vector)

Este é um simulador de redes focado em roteamento baseado no protocolo de Vetor de Distância (Distance Vector). Ele simula o comportamento de múltiplos roteadores operando em uma rede, trocando tabelas de rotas periodicamente e tomando decisões de encaminhamento.

## Requisitos

- Python 3.8+
- Bibliotecas externas utilizadas: `flask`, `requests`

Para instalar as dependências necessárias:
```bash
pip install flask requests
```

## Como Executar

O simulador suporta comunicação distribuída baseada em portas no localhost (`127.0.0.1`). Para iniciar a simulação completa usando a topologia de exemplo:

```bash
python main.py --file example_network/network.json
```

Com o comando acima, todos os roteadores definidos no JSON serão iniciados em background (daemon). Os logs unificados poderão ser acompanhados no arquivo temporário `/tmp/router_logs/global_routers.log`.

### Modo CLI Interativo (Recomendado)

O projeto possui uma interface de linha de comando (CLI) fácil de usar para visualizar rotas, enviar pacotes e testar o funcionamento da rede em tempo real.

```bash
python main.py --file example_network/network.json --cli
```

No menu principal, você encontrará as seguintes opções:
1. **Consultar Tabela de Roteamento**: Mostra a tabela de um roteador em tempo real. Exibe separadamente a "Tabela Completa" e a "Tabela Sumarizada" (que é a versão enviada aos vizinhos após aplicar as regras de vetor).
2. **Enviar Pacote**: Permite simular o envio de um dado a partir de um roteador origem até um IP/Rede de destino. O sistema retorna o sucesso da entrega e exibe um rastreamento (`TRACE_ID`), indicando todo o caminho (hops) percorrido.
3. **Visualizar Todos os Logs**: Abre os logs intercalados de todos os roteadores na sua tela utilizando o utilitário do sistema, útil para ver o tráfego do control plane.
4. **Ligar/Desligar Roteador (Simular Queda)**: Inativa (derruba) ou reativa um roteador sob demanda. Com isso, os vizinhos percebem a interrupção, ajustam o custo para infinito e recalculam novos caminhos.

### Flags e Argumentos Auxiliares

- `--interval <segundos>`: Define a frequência de broadcast das tabelas (Padrão: 10 segundos).
- `--no-split-horizon`: Desativa o mecanismo de prevenção de loop *Split Horizon*. Útil caso queira observar gargalos de Count-to-Infinity ou comparar tamanhos de pacotes de anúncio.

## Funcionalidades Implementadas

- **Protocolo Distance Vector**: Atualização paralela das tabelas buscando localizar sempre o salto de menor métrica para dada subrede.
- **Split Horizon**: Rotas aprendidas através de uma determinada interface/vizinho não são anunciadas de volta ao próprio vizinho, otimizando os broadcasts e fechando loops bidirecionais curtos.
- **Sumarização de Rotas Dinâmica**: Redes semanticamente vizinhas e de mesmo next-hop (ex: `10.0.1.0/24` e `10.0.0.0/24`) executam bitwise merge progressivo para se transformarem em supernets (ex: `10.0.0.0/23`) antes do anúncio, mantendo as tabelas do cluster o mais magras possível.
- **Recuperação de Falhas e Implicit Withdrawal**:
  - Se a comunicação com um vizinho falhar contíguas vezes, as rotas que dependiam exclusivamente dele são ajustadas pro custo máximo (infinito). Custos infinitos são propagados no próximo ciclo limpando a rede inteira em cascata.
  - Se um vizinho emite um pacote de atualizações sem rotas mais antigas (exemplo: ele trocou por sumarização), essas rotas finas antigas são removidas no receptor ("Implicit Route Withdrawal").
- **Packet Tracing e Logging Direcionado**: O sistema captura centralmente todos os rastros injetando uuid `trace_id` e exibindo via interface CLI as etapas exatas do encaminhamento (encapsulando stdout poluído sem uso de tela gráfica).

## Anatomia do Ambiente Base

A rede simulada inteira é mapeada em `example_network/network.json`:

```json
{
    "routers": [
        {
            "name": "RouterA",
            "network": "10.0.0.0/24",
            "address": "127.0.0.1:5000",
            "neighbors_csv": "example_network/router_a.csv"
        }
        ...
    ]
}
```

E cada descritor `.csv` constrói o estado de conectividade link-local físico inicial:
```csv
address,cost
127.0.0.1:5001,2
127.0.0.1:5002,5
```
