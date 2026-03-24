# CLI package for HordeForge

# Re-export functions from horde_cli for backwards compatibility
import requests

from cli.horde_cli import (
    EXIT_ERROR as EXIT_ERROR,
)
from cli.horde_cli import (
    EXIT_OK as EXIT_OK,
)
from cli.horde_cli import (
    EXIT_USAGE_ERROR as EXIT_USAGE_ERROR,
)
from cli.horde_cli import (
    build_main_parser as build_main_parser,
)
from cli.horde_cli import (
    build_parser as build_parser,
)
from cli.horde_cli import (
    check_gateway_health as check_gateway_health,
)
from cli.horde_cli import (
    get_run_status as get_run_status,
)
from cli.horde_cli import (
    main as main,
)
from cli.horde_cli import (
    trigger_pipeline as trigger_pipeline,
)

# Re-export requests for tests
requests = requests
