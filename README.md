# 🗳️ DashEleicoes2026 — Dashboard Eleições Gerais 2026 SP

Pipeline Python de coleta, processamento e visualização dos dados das
**Eleições Gerais 2026** para o município de **São Paulo**.

---

## 📋 Cargos monitorados

| Cargo | Abrangência |
|---|---|
| 🏛️ Presidente da República | Nacional (filtrado por SP) |
| 🏢 Governador | Estado de SP |
| 🎙️ Senador | Estado de SP |
| 🏠 Deputado Federal | Estado de SP |
| 🏛 Deputado Estadual | Estado de SP |

---

## 🚀 Instalação

```bash
pip install -r requirements.txt
```

---

## 🖥️ Comandos

```bash
# 1. Inicializar banco de dados
python main.py setup

# 2. Coletar candidatos (executar HOJE, pré-pleito)
python main.py candidatos

# 3. Testar conectividade com TSE
python main.py check

# 4. Iniciar polling automático (executar amanhã às 8h)
python main.py scheduler

# 5. Abrir dashboard (em outro terminal)
python main.py dashboard

# 6. Importar Boletins de Urna auditados (após 17h)
python main.py bu

# 7. Executar auditoria BU vs. Totalização
python main.py auditoria
```

---

## 📅 Ordem de execução

### Hoje (03/10/2026 — pré-pleito)
```
python main.py setup
python main.py candidatos
python main.py check
```

### Amanhã (04/10/2026 — dia do pleito)
```
# Terminal 1 — a partir das 8h
python main.py scheduler

# Terminal 2 — a qualquer momento
python main.py dashboard
```

### Pós-apuração (após 17h)
```
python main.py bu          # Importar BUs auditados
python main.py auditoria   # Cruzar BU vs TSE
```

---

## 🗄️ Estrutura do banco (SQLite)

| Tabela | Conteúdo |
|---|---|
| `candidatos` | Candidatos registrados (DivulgaCandContas) |
| `resultados` | Snapshots de votos por candidato (5 em 5 min) |
| `boletins_urna` | Votos auditados dos BUs físicos |
| `snapshots_meta` | Totais por cargo (brancos, nulos, válidos) |

---

## 🔗 Fontes de dados

| Portal | URL |
|---|---|
| Resultados TSE (tempo real) | https://resultados.tse.jus.br |
| Dados Abertos TSE | https://dadosabertos.tse.jus.br |
| DivulgaCandContas | https://divulgacandcontas.tse.jus.br |

---

## ⚙️ Variáveis de ambiente

| Variável | Padrão | Descrição |
|---|---|---|
| `TSE_PLEITO_1T` | `3220` | Código do pleito 1º turno 2026 |
| `LOG_LEVEL` | `INFO` | Nível de log |

> **Nota:** O código real do pleito será descoberto automaticamente via
> `GET https://resultados.tse.jus.br/ele2026/config.json` ao iniciar o scheduler.
