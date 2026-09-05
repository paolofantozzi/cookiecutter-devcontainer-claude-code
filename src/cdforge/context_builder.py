from __future__ import annotations

import re
from datetime import UTC
from datetime import datetime
from typing import Any

from cdforge import __version__
from cdforge.project_types import data_science
from cdforge.project_types import django_drf
from cdforge.project_types import python_uv_tool
from cdforge.project_types.base import ProjectType

_DERIVE_DEFAULTS = {
    'python_uv_tool': python_uv_tool.derive_defaults,
    'django_drf': django_drf.derive_defaults,
    'data_science': data_science.derive_defaults,
}


def slugify(raw: str) -> str:
    slug = re.sub(r'[^a-zA-Z0-9]+', '-', raw.strip()).strip('-').lower()
    return slug or 'project'


def build_context(
    answers: dict[str, Any],
    project_type: ProjectType,
    optional_skill_ids: list[str],
) -> dict[str, Any]:
    context: dict[str, Any] = dict(answers)
    derive = _DERIVE_DEFAULTS.get(project_type.id)
    if derive is not None:
        for key, value in derive(answers).items():
            context.setdefault(key, value)

    for question in project_type.questions:
        context.setdefault(question.key, question.resolve_default())

    context.setdefault('project_slug', slugify(context['project_name']))
    context.setdefault('git_remote_url', '')
    context.setdefault('gpu_enabled', False)

    # Projects that need backing services (Postgres/Redis) get them as *sibling*
    # containers via the Dev Containers Docker Compose workflow: the devcontainer itself
    # stays an ordinary, unprivileged container that can only reach the workspace, and the
    # services live on the compose network (reachable by hostname, never on the host FS).
    context['use_compose'] = bool(
        project_type.id == 'django_drf'
        and (context.get('database') == 'postgres' or context.get('include_celery'))
    )

    # Where the generated compose file lives:
    #   'root'         - `docker-compose.yml` at the project root (a fresh project).
    #   'devcontainer' - `.devcontainer/docker-compose.cdforge.yml`, loaded as an *override*
    #                    on top of a compose file the adopted project already had, so its
    #                    own services survive and the devcontainer's `app` service is added.
    #                    Compose resolves relative paths in every file against the first
    #                    file's directory, so the override's paths still mean the root.
    compose_file_location = context.get('compose_file_location')
    if compose_file_location not in ('root', 'devcontainer'):
        compose_file_location = 'root'
    context['compose_file_location'] = compose_file_location
    context['compose_files'] = (
        ['../docker-compose.yml']
        if compose_file_location == 'root'
        else ['../docker-compose.yml', 'docker-compose.cdforge.yml']
    )

    # How (if at all) Claude Code can run its own containers inside the devcontainer:
    #   'none'       - no in-container Docker (default, maximum sandbox).
    #   'sysbox'     - a full Docker daemon runs inside, isolated by the sysbox runtime
    #                  (user-namespaced): no --privileged, no host access. Requires sysbox
    #                  installed on the host.
    #   'privileged' - the docker-in-docker feature, which forces --privileged and REMOVES
    #                  host isolation.
    docker_mode = context.get('docker_mode')
    if docker_mode not in ('none', 'sysbox', 'privileged'):
        # Backward compatibility with the older boolean answer.
        docker_mode = 'privileged' if context.get('enable_docker') else 'none'
    context['docker_mode'] = docker_mode
    # `enable_docker` now specifically means "the privileged docker-in-docker feature".
    context['enable_docker'] = docker_mode == 'privileged'

    # Egress control for the devcontainer:
    #   'none'      - no restriction (the default, and what any devcontainer does out of the
    #                 box): the container can reach the internet, the host's LAN, and the
    #                 host itself through the Docker bridge gateway.
    #   'allowlist' - `.devcontainer/init-firewall.sh` rejects egress to the Docker gateway
    #                 (so the host's own listening ports stop being reachable) and to
    #                 anything not on the allowlist. It needs NET_ADMIN/NET_RAW, and the base
    #                 image keeps its passwordless sudo, so in-container root can still flush
    #                 the rules: it stops incidental traffic, not a determined process.
    #   'strict'    - 'allowlist' plus removing the base image's blanket NOPASSWD sudo,
    #                 leaving one rule for the firewall script alone (baked into the image as
    #                 /usr/local/bin/cdforge-firewall, root-owned and unwritable from inside),
    #                 so the rules cannot be undone from within the container. In-container
    #                 Docker needs root at runtime, so 'strict' degrades to 'allowlist'
    #                 whenever docker_mode is not 'none'.
    network_firewall = context.get('network_firewall')
    if network_firewall not in ('none', 'allowlist', 'strict'):
        network_firewall = 'none'
    if network_firewall == 'strict' and docker_mode != 'none':
        network_firewall = 'allowlist'
    context['network_firewall'] = network_firewall
    context['firewall_enabled'] = network_firewall in ('allowlist', 'strict')

    # runArgs for the plain (non-compose) layout. In the compose layout the runtime/privilege
    # is expressed on the `app` service instead.
    run_args: list[str] = []
    if context['gpu_enabled'] and not context['use_compose']:
        run_args.append('--gpus=all')
    if docker_mode == 'sysbox' and not context['use_compose']:
        run_args.append('--runtime=sysbox-runc')
    if context['firewall_enabled'] and not context['use_compose']:
        # iptables inside the container needs NET_ADMIN; NET_RAW is already in Docker's
        # default set but is named here so the requirement is explicit.
        run_args += ['--cap-add=NET_ADMIN', '--cap-add=NET_RAW']
    context['run_args'] = run_args

    # postStartCommand runs on every container start. Docker first (the sysbox mode fetches
    # its installer over the network), the firewall last, so it is the final word on egress.
    post_start_commands: list[str] = []
    if docker_mode in ('sysbox', 'privileged'):
        post_start_commands.append('bash .devcontainer/docker-start.sh')
    if context['firewall_enabled']:
        post_start_commands.append('sudo /usr/local/bin/cdforge-firewall')
    context['post_start_command'] = ' && '.join(post_start_commands)

    context['project_type'] = project_type.id
    context['project_type_label'] = project_type.label
    context['remote_user'] = project_type.remote_user
    context['base_image'] = project_type.base_image
    extra_apt_packages = list(project_type.extra_apt_packages)
    if context['firewall_enabled'] and 'iptables' not in extra_apt_packages:
        extra_apt_packages.append('iptables')
    context['extra_apt_packages'] = extra_apt_packages
    context['extra_features'] = project_type.extra_features
    context['forward_ports'] = list(project_type.forward_ports)
    context['vscode_extensions'] = list(project_type.vscode_extensions)
    context['extra_allowed_domains'] = list(project_type.extra_allowed_domains)
    context['optional_skills'] = optional_skill_ids
    context['cdforge_version'] = __version__
    context['generation_year'] = datetime.now(tz=UTC).year

    return context
