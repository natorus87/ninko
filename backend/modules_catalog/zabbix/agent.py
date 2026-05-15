"""Zabbix module agent."""

from agents.base_agent import BaseAgent
from modules_catalog.zabbix import tools


class ZabbixAgent(BaseAgent):
    """Zabbix Monitoring Agent."""

    name = "zabbix"
    description = {
        "de": "Zabbix Enterprise Monitoring – Hosts, Items, Triggers, Graphs und Alerts",
        "en": "Zabbix Enterprise Monitoring – Hosts, Items, Triggers, Graphs and Alerts",
        "fr": "Zabbix Enterprise Monitoring – Hôtes, Items, Déclencheurs, Graphiques et Alertes",
        "es": "Zabbix Enterprise Monitoring – Hosts, Items, Triggers, Gráficos y Alertas",
        "it": "Zabbix Enterprise Monitoring – Host, Item, Trigger, Grafici e Allarmi",
        "nl": "Zabbix Enterprise Monitoring – Hosts, Items, Triggers, Grafieken en Alerts",
        "pl": "Zabbix Enterprise Monitoring – Hosty, Elementy, Wyzwalacze, Wykresy i Alerty",
        "pt": "Zabbix Enterprise Monitoring – Hosts, Itens, Triggers, Gráficos e Alertas",
        "ja": "Zabbix エンタープライズモニタリング – ホスト、アイテム、トリガー、グラフ、アラート",
        "zh": "Zabbix企业监控 – 主机、监控项、触发器、图形和告警",
    }
    system_prompt = """You are Ninko's Zabbix monitoring specialist.

Capabilities:
- Query host status and metrics
- Analyse monitoring data and trends
- Manage triggers and alerts
- Create graphs and reports
- Configure hosts and items

Tool execution rules:
- Always call the available Zabbix tools to query and analyse data.
- Never rely on general knowledge for live Zabbix state.

Output format:
- For lists (Hosts, Items, Triggers, Alerts, Graphs): ALWAYS use Markdown tables.
- Example header: | Host | Status | Items |
- NEVER return bullet lists, plain text, or raw JSON.
- Always include units for numerical values (ms, %, GB, etc.).
- Color-code status and severity/priority when helpful.

Safety and confirmation rules:
- Host creation or deletion requires explicit confirmation.

Error handling:
- If a query returns no data, say so clearly and suggest a concrete next step."""

    def __init__(self) -> None:
        """Initialize the Zabbix agent with its BaseAgent contract."""
        super().__init__(
            name="zabbix",
            system_prompt=self.system_prompt,
            tools=[
                tools.get_zabbix_status,
                tools.list_zabbix_hosts,
                tools.get_zabbix_host,
                tools.list_zabbix_items,
                tools.list_zabbix_triggers,
                tools.get_zabbix_problems,
                tools.list_zabbix_graphs,
                tools.list_zabbix_actions,
                tools.get_zabbix_history,
                tools.get_zabbix_host_group,
                tools.list_zabbix_templates,
                tools.create_zabbix_host,
                tools.delete_zabbix_host,
            ],
        )


agent = ZabbixAgent()
