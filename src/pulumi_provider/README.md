# itl-attestation-pulumi

Pulumi dynamic provider for the [ITL Control Plane Attestation Service](https://github.com/ITlusions/ITL.ControlPlane.Attestation).

Wraps the Attestation REST API as first-class Pulumi resources, enabling machine registration and approval to be managed declaratively in infrastructure-as-code stacks.

## Resources

| Resource | Description |
|---|---|
| `RegisteredMachine` | Registers a node with the Attestation Service |
| `MachineApproval` | Approves a pending attestation request |

## Usage

```python
import pulumi
from pulumi_provider import RegisteredMachine, MachineApproval, NodeRole

machine = RegisteredMachine(
    "my-node",
    hostname="node-01.example.com",
    role=NodeRole.WORKER,
)

approval = MachineApproval(
    "my-node-approval",
    machine_id=machine.machine_id,
)
```

## Requirements

- Python >= 3.10
- `pulumi >= 3.0.0, < 4.0.0`
- `itl-attestation-sdk >= 0.1.0`

## Installation

```bash
pip install itl-attestation-pulumi
```
