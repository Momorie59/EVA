from pathlib import Path

from .tools.base import Tool
from .tools.docker_tools import (
    DockerLogsTool,
    DockerPsTool,
    DockerRestartTool,
    DockerStartTool,
    DockerStopTool,
)
from .tools.dev_tools import DevCheckTool, FsEditTool, FsGrepTool, FileDeliverTool, FsTreeTool, ZipMakeTool
from .tools.docs_tool import DocsSearchTool
from .tools.telegram_tools import TelegramNotifyTool
from .tools.question_tools import PoserQuestionTool
from .tools.plan_tools import PlanTachesTool
from .tools.recherche_tools import RechercheApprofondieTool
from .tools.fond_tools import TacheDeFondTool
from .tools.satellite_tools import AnnonceTool, ChromePcTool, PcCommandeTool, PcEcranCliquerTool, PcEcranVoirTool, PcOperateurTool, TelephoneSonnerTool
from .tools.agenda_tools import AgendaIcsTool
from .tools.contenus_tools import ContenuAvancerTool, ContenuIdeeTool, ContenuListerTool
from .tools.finances_tools import FinancesBudgetTool, FinancesNoterTool, FinancesOperationsTool, FinancesResumeTool
from .tools.spotify_tools import SpotifyCommandeTool, SpotifyEnCoursTool, SpotifyJouerTool
from .tools.document_tools import DocumentCreerTool, DocumentModifierTool
from .tools.navigateur_tools import NavigateurCaptureTool, NavigateurCliquerTool, NavigateurLireTool, NavigateurOuvrirTool, NavigateurRemplirTool
from .tools.connecteurs_tools import AppelTelephoneTool, DiscordEnvoyerTool, InstagramStatsTool, ObsActionTool, ObsEtatTool
from .tools.image_tools import ImageEditTool, ImageGenerateTool, VideoGenerateTool
from .tools.ha_tools import HaCallTool, HaGetTool, HaStatesTool
from .tools.home_tools import DeviceControlTool, DeviceListTool, HueSceneTool, PresenceTool, SceneRunTool
from .tools.list_tools import ListAddTool, ListCheckTool, ListRemoveTool, ListShowTool
from .tools.net_tools import NetDiscoverTool, NetHostsTool, NetHttpTool, NetInspectTool, NetProbeTool, NetScanTool, NetSshTool
from .tools.print_tools import PrintFileTool, PrintListTool, PrintTextTool, PrinterListTool
from .tools.google_tools import CalendarCreateTool, CalendarListTool, CalendarModifierTool, CalendarSupprimerTool, GmailColisTool, GmailReadTool, GmailSearchTool, GmailSendTool
from .tools.self_tools import SelfProposeTool, SelfReadTool
from .tools.delegate import DelegateTool
from .tools.roles import RoleRunTool
from .tools.code_run import CodeRunTool
from .tools.filesystem import FsAppendTool, FsDeleteTool, FsListTool, FsReadTool, FsWriteTool
from .tools.project_docs import ProjectInitTool, ProjectLogChangeTool, ProjectLogDecisionTool
from .tools.git_tools import GitCommitTool, GitDiffTool, GitLogTool, GitStatusTool
from .tools.github_tools import GithubInfoTool
from .tools.skills_tools import SkillInstallTool, SkillListTool, SkillReadTool, SkillSaveTool
from .tools.system_stats import SystemStatsTool
from .tools.aiserver_tool import AiServerStatsTool
from .tools.sandbox_tools import SandboxDbTool, SandboxInstallTool, SandboxRunTool
from .tools.terminal import TerminalTool
from .tools.weather import WeatherTool
from .tools.present import PresentTool
from .tools.notes_tools import NoteCreateTool, NoteDeleteTool, NoteListTool, NoteUpdateTool
from .tools.api_tools import ApiGetTool, ApiSearchTool
from .tools.web import WebFetchTool, WebSearchTool
from .tools import papiers_tools
from .tools import memoire_tools
from .tools import wiki_tools
from .tools import rappel_tools
from .tools import routine_tools
from .tools import tv_tools
from .tools import agent_tools
from .tools import carnet_tools
from .tools.evolution_tools import EvolutionDemanderTool
from .tools import recette_tools
from .tools.code_agent_tool import CodeAgentTool


class ToolRegistry:
    def __init__(self, workspace_root: Path):
        tools: list[Tool] = [
            FsListTool(workspace_root),
            FsReadTool(workspace_root),
            FsWriteTool(workspace_root),
            FsAppendTool(workspace_root),
            FsDeleteTool(workspace_root),
            FsTreeTool(workspace_root),
            FsGrepTool(workspace_root),
            FsEditTool(workspace_root),
            DevCheckTool(workspace_root),
            ZipMakeTool(workspace_root),
            FileDeliverTool(workspace_root),
            ProjectInitTool(workspace_root),
            ProjectLogDecisionTool(workspace_root),
            ProjectLogChangeTool(workspace_root),
            WeatherTool(),
            PresentTool(),
            DockerPsTool(),
            DockerLogsTool(),
            DockerRestartTool(),
            DockerStopTool(),
            DockerStartTool(),
            SystemStatsTool(),
            AiServerStatsTool(),
            TerminalTool(workspace_root),
            ImageGenerateTool(workspace_root),
            ImageEditTool(workspace_root),
            VideoGenerateTool(workspace_root),
            WebSearchTool(),
            WebFetchTool(),
            ApiSearchTool(),
            ApiGetTool(),
            GitStatusTool(workspace_root),
            GithubInfoTool(workspace_root),
            GitLogTool(workspace_root),
            GitDiffTool(workspace_root),
            GitCommitTool(workspace_root),
            SkillListTool(workspace_root),
            SkillReadTool(workspace_root),
            SkillSaveTool(workspace_root),
            SkillInstallTool(workspace_root),
            DocsSearchTool(),
            CodeRunTool(),
            SandboxRunTool(workspace_root),
            SandboxInstallTool(workspace_root),
            SandboxDbTool(workspace_root),
            SelfReadTool(),
            HaStatesTool(),
            HaGetTool(),
            HaCallTool(),
            DeviceListTool(),
            DeviceControlTool(),
            SceneRunTool(),
            HueSceneTool(),
            PresenceTool(),
            ListShowTool(),
            ListAddTool(),
            ListCheckTool(),
            ListRemoveTool(),
            PrinterListTool(),
            PrintTextTool(),
            PrintFileTool(workspace_root),
            PrintListTool(),
            NetHostsTool(),
            NetScanTool(),
            NetDiscoverTool(),
            NetProbeTool(),
            NetHttpTool(),
            NetSshTool(),
            NetInspectTool(),
            GmailSearchTool(),
            GmailColisTool(),
            GmailReadTool(),
            GmailSendTool(),
            CalendarListTool(),
            CalendarCreateTool(),
            CalendarModifierTool(),
            CalendarSupprimerTool(),
            SelfProposeTool(),
            TelegramNotifyTool(),
            ObsEtatTool(),
            ObsActionTool(),
            DiscordEnvoyerTool(),
            InstagramStatsTool(),
            AppelTelephoneTool(),
            PoserQuestionTool(),
            PlanTachesTool(),
            RechercheApprofondieTool(),
            TacheDeFondTool(),
            AgendaIcsTool(),
            FinancesResumeTool(),
            ContenuIdeeTool(),
            ContenuListerTool(),
            ContenuAvancerTool(),
            FinancesOperationsTool(),
            FinancesNoterTool(),
            FinancesBudgetTool(),
            SpotifyEnCoursTool(),
            AnnonceTool(),
            PcCommandeTool(),
            PcEcranVoirTool(),
            PcEcranCliquerTool(),
            PcOperateurTool(),
            TelephoneSonnerTool(),
            ChromePcTool(),
            SpotifyJouerTool(),
            SpotifyCommandeTool(),
            DocumentCreerTool(workspace_root),
            DocumentModifierTool(workspace_root),
            NavigateurOuvrirTool(),
            NavigateurLireTool(),
            NavigateurCaptureTool(),
            NavigateurCliquerTool(),
            NavigateurRemplirTool(),
            DelegateTool(),
            RoleRunTool(workspace_root),
            NoteCreateTool(),
            NoteListTool(),
            NoteUpdateTool(),
            NoteDeleteTool(),
        ]
        tools += memoire_tools.all_tools()
        tools += wiki_tools.all_tools()
        tools += recette_tools.all_tools()
        tools += rappel_tools.all_tools()
        tools += routine_tools.all_tools()
        tools += tv_tools.all_tools()
        tools += agent_tools.all_tools()
        tools += carnet_tools.all_tools()
        tools.append(EvolutionDemanderTool())
        tools.append(CodeAgentTool(workspace_root))
        tools += papiers_tools.all_tools(workspace_root)   # papiers : répondent « pas configurés » tant que Paperless n'est pas réglé
        self._by_name = {t.name: t for t in tools}
        self._dynamic: dict[str, Tool] = {}  # outils MCP, remplacés à chaque rafraîchissement
        self._plugins: dict[str, Tool] = {}  # outils des plugins activés (app/plugins.py)

    def set_dynamic(self, tools: list[Tool]) -> None:
        self._dynamic = {t.name: t for t in tools if t.name not in self._by_name}

    def set_plugins(self, tools: list[Tool]) -> None:
        self._plugins = {t.name: t for t in tools if t.name not in self._by_name}

    def _all(self) -> dict[str, Tool]:
        return {**self._by_name, **self._dynamic, **self._plugins}

    def get(self, name: str) -> Tool | None:
        t = self._all().get(name)
        return None if t is not None and t.agents_only else t

    def get_any(self, name: str) -> Tool | None:
        """Accès complet, y compris aux outils réservés aux agents."""
        return self._all().get(name)

    def names(self) -> list[str]:
        return [n for n, t in self._all().items() if not t.agents_only]

    def all_names(self) -> list[str]:
        return list(self._all().keys())

    def schemas(self) -> list[dict]:
        return [t.schema() for t in self._all().values() if not t.agents_only]
