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
- `--no-fail-protection`: Desativa os mecanismos proativos de tolerância a falhas do roteador. Remove o monitoramento de *timeouts* (`_handle_neighbor_down`) e deleta a regra de *Implicit Route Withdrawal*, fixando conexões falhas no estado de timeout persistente simulado.

## 🛠️ Entendendo as Funcionalidades (Visão Detalhada)

O simulador implementa conceitos reais de redes de computadores. Abaixo está uma explicação passo a passo de como cada mecanismo opera debaixo dos panos:

### 1. Protocolo Distance Vector (Vetor de Distância)
Neste modelo de roteamento dinâmico, os roteadores não conhecem a topologia inteira da rede (como fariam no OSPF). Eles conhecem apenas os **seus vizinhos diretos** e o custo do link até eles.
A cada ciclo de tempo (`--interval`), um roteador envia sua tabela inteira para os vizinhos contendo: "Destino" e "Custo". 
O vizinho recebe isso e aplica a equação de Bellman-Ford: se o Custo anunciado + Custo até o vizinho for **menor** do que a rota que ele já tem anotada (ou se ele não conhecia essa rede), ele salva essa nova rota apontando para esse vizinho. 
Em algumas rodadas de troca de mensagens, a rede converge e todos descobrem o caminho mais barato para qualquer sub-rede.

### 2. A Queda e o Custo Infinito
Em uma rede real, os cabos podem romper ou roteadores podem desligar. O simulador lida com isso da seguinte forma:
- Se o **Router A** tenta enviar um broadcast periódico para o **Router B** e o B não responde (`timeout`), o Router A conclui que o link caiu.
- Imediatamente, o Router A varre sua tabela de roteamento. Qualquer destino cujo `next_hop` fosse o Router B tem seu **custo alterado para Infinito** (`float('inf')`).
- No próximo ciclo de anúncios, o Router A avisa ao resto da rede: *"Para chegar naquelas sub-redes através de mim, o custo agora é infinito"*.
- Os outros roteadores recebem essa atualização e, como o custo deles pra lá aumentou, eles vão substituir essa rota morta assim que outro vizinho anunciar um caminho alternativo válido.
*(Use `--no-fail-protection` para desativar esse comportamento preventivo).*

### 3. Remoção de Rotas (Implicit Withdrawal)
O Vector Distance confia cegamente que as rotas continuarão sendo renovadas pelos vizinhos. 
Se o Router A aprendeu que existe a rede `10.0.1.0/24` através do Router B, ele espera que em toda atualização o Router B envie essa rota novamente.
Se por acaso o Router B **parar de enviar** essa rede específica (por exemplo, porque ela foi sumarizada em um prefixo maior), o Router A aplica um "Withdrawal" (Retirada). Ele percebe a ausência da rota na tabela do vizinho que o ensinou, deduz que o caminho para aquele prefixo exato não existe mais via aquele nó, e **deleta a entrada** de sua própria tabela.

### 4. O Problema do "Split Horizon"
Na família de protocolos de vetor de distância (como o RIP clássico), há um problema grave conhecido como **Count-to-Infinity**. Acontece quando:
1. O Router A vai pro destino X através do Router B (custo 2).
2. O Router B perde a ligação direta com X. Seu custo vai para Infinito.
3. Antes do Router B conseguir avisar que a rota caiu, o Router A manda seu anúncio para o Router B dizendo "Eu chego em X com custo 2". 
4. O Router B sabe que ele se conecta no A com custo 1. Ele ouve o A e pensa: *"Opa! Achei um caminho alternativo! Se o A chega com custo 2, eu chego por ele com custo 3!"*. 
5. Em loop cíclico, B atualiza A que atualiza B num ciclo que cresce ao infinito.

O mecanismo de **Split Horizon** impede isso com uma regra de ouro: **Nunca anuncie uma rota de volta pela mesma interface/vizinho de onde você a aprendeu**. O Router A omite a rota de X quando envia seus dados para o Router B, cortando o loop de retroalimentação elástica. 
*(Para causar o problema propositalmente e travar a rede, inicie todos com `--no-split-horizon`)*.

### 5. Sumarização de Rotas (Route Summarization / CIDR)
À medida que a rede cresce, manter dezenas de prefixos /24 na tabela de roteamento exige muita carga computacional.
O simulador implementa um algoritmo de compressão interativa:
- Se um roteador percebe que tem na tabela as rotas `10.0.0.0/24` e `10.0.1.0/24` (que são adjacentes binariamente), que possuem o **mesmo next_hop** e o mesmo custo.
- Ele **combina** esses dois escopos e gera o super-bloco subjacente: `10.0.0.0/23`.
- Ao anunciar para os vizinhos, ele invia apenas a `/23`. Combinado com o *Implicit Withdrawal*, o vizinho apaga as memórias antigas `/24` e armazena apenas o CIDR amplo, enxugando sua própria tabela de rotas.

### 6. Packet Tracing Interativo
Ao usar a opção de "Enviar Pacote" via CLI, o servidor HTTP insere um ID de UUID único (`trace_id`) dentro do corpo JSON do payload original.
A partir daí, como os nós da aplicação redirecionam a chamada HTTP de nó em nó pelas diretrizes da Routing Table, eles fazem um Log explícito contendo esse ID em cada etapa.
A CLI escaneia o log global buscando por aquele identificador exato e exibe para você o mapa completo de cada roteador pelo qual a mensagem HTTP transitou até alcançar à sub-rede destino ou ser despachada no vazio.

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
