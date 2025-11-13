"""
SSH Helper utilities for diagnostic scripts.

Provides common SSH authentication handling for all diagnostic tools.
"""

import shutil
from typing import List, Optional


def build_ssh_command(
    ip: str,
    remote_command: str,
    username: str = "neuroam",
    password: Optional[str] = None,
    timeout: int = 2
) -> List[str]:
    """
    Build SSH command with appropriate authentication method.
    
    Args:
        ip: IP address
        remote_command: Command to run on remote host
        username: SSH username
        password: SSH password (if None, will try key-based auth)
        timeout: Connection timeout
        
    Returns:
        List of command arguments
    """
    ssh_opts = [
        "-o", f"ConnectTimeout={timeout}",
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "LogLevel=ERROR"
    ]
    
    use_sshpass = password is not None and shutil.which("sshpass") is not None
    
    if use_sshpass:
        return ["sshpass", "-p", password, "ssh"] + ssh_opts + [f"{username}@{ip}", remote_command]
    else:
        return ["ssh"] + ssh_opts + [f"{username}@{ip}", remote_command]


def check_sshpass() -> bool:
    """Check if sshpass is available."""
    return shutil.which("sshpass") is not None


def print_sshpass_warning():
    """Print warning message if sshpass is not available."""
    if not check_sshpass():
        print("⚠️  Warning: sshpass not found. Install it for password authentication:")
        print("   sudo apt-get install sshpass")
        print("   Trying key-based authentication instead...\n")
