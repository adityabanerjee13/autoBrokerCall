"""Dograh - the agent orchestrator.

Dograh owns the call itself: the VoBiz carrier leg, Azure Speech in both
directions, and the workflow graph that decides what the agent says. All three
are configured inside Dograh, so nothing in this package holds a carrier or
speech credential - only a Dograh API key.

  client.py     outbound: hand a call over, fetch the result
  api/dograh.py inbound: the agent's tool calls, and the completion webhook
"""
