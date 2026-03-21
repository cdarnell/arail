#!/usr/bin/env python3
"""
Hardware Probe and Values.yaml Auto-Tuner
Supports Linux, macOS, and Windows.
Generates `helm/k8s-lite/values.generated.yaml` or applies updates to `helm/k8s-lite/values.yaml` with --apply.

Requires: pyyaml, psutil

Usage:
  python hardware_probe.py --output helm/k8s-lite/values.generated.yaml
  python hardware_probe.py --apply  # overwrites helm/k8s-lite/values.yaml after prompting
"""
from __future__ import annotations
import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

try:
    import psutil
    import yaml
except Exception:
    print("Missing dependencies. Please run: pip install -r requirements.txt")
    sys.exit(2)

ROOT = Path(__file__).resolve().parents[2]
VALUES_PATH = ROOT / 'helm' / 'k8s-lite' / 'values.yaml'
OUTPUT_DEFAULT = ROOT / 'helm' / 'k8s-lite' / 'values.generated.yaml'


def run_cmd(cmd):
    try:
        out = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL, universal_newlines=True)
        return out.strip()
    except Exception:
        return ''


def detect_cpu():
    info = {}
    info['platform_system'] = platform.system()
    info['processor'] = platform.processor() or ''
    try:
        info['physical_cores'] = psutil.cpu_count(logical=False) or 1
        info['logical_cores'] = psutil.cpu_count(logical=True) or info['physical_cores']
    except Exception:
        info['physical_cores'] = 1
        info['logical_cores'] = 1

    # try more detailed on Linux
    if info['platform_system'] == 'Linux':
        lscpu = run_cmd('lscpu')
        if lscpu:
            m = re.search(r"^Model name:\s*(.+)$", lscpu, flags=re.M)
            if m:
                info['model'] = m.group(1).strip()
    elif info['platform_system'] == 'Darwin':
        info['model'] = run_cmd("sysctl -n machdep.cpu.brand_string")
    elif info['platform_system'] == 'Windows':
        info['model'] = run_cmd('wmic cpu get Name /value')
    return info


def detect_ram():
    v = psutil.virtual_memory()
    return {'total_bytes': int(v.total)}


def detect_gpus():
    gpus = []
    # NVIDIA via nvidia-smi
    nvsmi = run_cmd('nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits')
    if nvsmi:
        for line in nvsmi.splitlines():
            parts = [p.strip() for p in line.split(',')]
            if len(parts) >= 2:
                gpus.append({'vendor': 'nvidia', 'name': parts[0], 'memory_mib': int(float(parts[1]))})
    # macOS: system_profiler SPDisplaysDataType
    if platform.system() == 'Darwin':
        sp = run_cmd('system_profiler SPDisplaysDataType -json')
        if sp:
            try:
                j = json.loads(sp)
                items = j.get('SPDisplaysDataType', [])
                for it in items:
                    name = it.get('sppci_model') or it.get('_name') or it.get('sppci_model')
                    if name:
                        gpus.append({'vendor': 'apple', 'name': name, 'memory_mib': None})
            except Exception:
                pass
    return gpus


def bytes_to_gib(b):
    return round(b / (1024 ** 3), 2)


def recommend(resources_profile, cpu_info, ram_info, gpus):
    """Return recommended per-component resource dict based on simple heuristics and user profiles."""
    total_gib = bytes_to_gib(ram_info['total_bytes'])
    physical = cpu_info.get('physical_cores', 1)
    logical = cpu_info.get('logical_cores', physical)

    # Base scaling factors
    scale = 1.0
    if physical >= 8:
        scale = 1.3
    elif physical >= 4:
        scale = 1.1

    has_nvidia = any(g['vendor'] == 'nvidia' for g in gpus)
    gpu_count = len(gpus)

    # Default recommendations (can be tuned)
    rec = {}
    rec['ollama'] = {
        'enabled': resources_profile.get('ollama', {}).get('enabled', True),
        'resources': {
            'limits': {'cpu': str(max(1, int(1 * scale))), 'memory': '4Gi', 'nvidia.com/gpu': 1 if has_nvidia else 0},
            'requests': {'cpu': str(max(1, int(0.5 * scale))), 'memory': '2Gi'},
        }
    }
    rec['lmdeploy'] = {
        'enabled': resources_profile.get('lmdeploy', {}).get('enabled', True),
        'resources': {
            'limits': {'cpu': str(max(2, int(2 * scale))), 'memory': '8Gi', 'nvidia.com/gpu': 1 if has_nvidia else 0},
            'requests': {'cpu': str(max(1, int(1 * scale))), 'memory': '2Gi'},
        },
        'env': {'MODEL_PATH': '/mnt/models/llama-3-8b'}
    }
    rec['n8n'] = {
        'enabled': resources_profile.get('n8n', {}).get('enabled', True),
        'persistence': {'enabled': True, 'size': '5Gi'},
        'env': [{'name': 'KAFKA_BROKERS', 'value': 'redpanda-0.redpanda.opencode.svc.cluster.local:9092'}],
        'resources': {
            'limits': {'cpu': '1', 'memory': '2Gi'},
            'requests': {'cpu': '0.5', 'memory': '1Gi'}
        }
    }
    rec['redpanda'] = {
        'enabled': resources_profile.get('redpanda', {}).get('enabled', True),
        'resources': {'limits': {'memory': '1Gi'}, 'requests': {'memory': '512Mi'}},
        'config': {'auto_create_topics': True}
    }
    rec['jupyterlab'] = {'enabled': resources_profile.get('jupyterlab', {}).get('enabled', True),
                        'resources': {'limits': {'cpu': '1', 'memory': '1Gi'}, 'requests': {'cpu': '0.5', 'memory': '512Mi'}}}
    rec['prometheus'] = {'enabled': resources_profile.get('prometheus', {}).get('enabled', True),
                         'resources': {'limits': {'cpu': '1', 'memory': '2Gi'}, 'requests': {'cpu': '0.5', 'memory': '1Gi'}},
                         'config': {'retention_period': '15d'}}
    rec['loki'] = {'enabled': resources_profile.get('loki', {}).get('enabled', True),
                   'config': {'retention_period': '72h'}}

    return rec


def merge_values(existing_vals: dict, recommendations: dict):
    vals = existing_vals.copy()
    comps = vals.get('components', {})
    for k, v in recommendations.items():
        if 'components' not in vals:
            vals['components'] = {}
        comps_k = comps.get(k, {})
        # Merge: prefer existing enabled flag if present
        merged = comps_k.copy()
        # Merge resources and other keys
        for subk, subv in v.items():
            if isinstance(subv, dict):
                merged.setdefault(subk, {}).update(subv)
            else:
                merged.setdefault(subk, subv)
        vals['components'][k] = merged
    return vals


def load_yaml(path: Path):
    if not path.exists():
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f) or {}


def write_yaml(path: Path, data):
    with open(path, 'w', encoding='utf-8') as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', '-o', default=str(OUTPUT_DEFAULT))
    p.add_argument('--apply', action='store_true', help='Overwrite helm/k8s-lite/values.yaml with recommended values (prompt)')
    args = p.parse_args()

    print('Detecting hardware...')
    cpu = detect_cpu()
    ram = detect_ram()
    gpus = detect_gpus()

    print(f"Platform: {cpu.get('platform_system')} | CPU model: {cpu.get('model') or cpu.get('processor')} | cores: {cpu.get('physical_cores')}/{cpu.get('logical_cores')}")
    print(f"RAM: {bytes_to_gib(ram['total_bytes'])} GiB | GPUs: {len(gpus)}")

    existing = load_yaml(VALUES_PATH) if VALUES_PATH.exists() else {}
    recommendations = recommend(existing.get('components', {}), cpu, ram, gpus)

    merged = merge_values(existing, recommendations)

    outp = Path(args.output)
    write_yaml(outp, merged)
    print(f'Wrote recommendations to {outp}')

    if args.apply:
        confirm = input(f'Apply recommendations and overwrite {VALUES_PATH}? (yes/NO): ').strip().lower()
        if confirm in ('yes', 'y'):
            backup = VALUES_PATH.with_suffix('.yaml.bak')
            shutil.copy2(VALUES_PATH, backup)
            write_yaml(VALUES_PATH, merged)
            print(f'Applied recommendations. Backup saved to {backup}')
        else:
            print('Aborted apply.')


if __name__ == '__main__':
    main()
