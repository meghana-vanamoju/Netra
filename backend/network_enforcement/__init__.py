"""Backend foundation for opt-in, per-device network enforcement.

Stage 1 only provides configuration, identity validation, safe command
builders, dry-run plans, and additive persistence. No command in this package
changes firewall, qdisc, interface, router, or host network state.
"""
