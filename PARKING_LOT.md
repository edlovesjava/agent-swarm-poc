# Parking Lot

Ideas and features parked for future consideration. These are out of scope for Phase 1 but worth exploring later.

---

## Multi-Repo Support

**Added:** 2025-01-10
**Status:** Parked
**Category:** Architecture
**Phase:** 3

### Concept

Enable agents to coordinate across multiple repositories, sharing file locks and understanding cross-repo dependencies.

### Use Cases

- Monorepo → multi-repo migrations
- Microservices with shared libraries
- Documentation repos linked to code repos

### Open Questions

- [ ] How to handle cross-repo file locks?
- [ ] Shared agent pool vs per-repo agents?
- [ ] Permission model across repos?

---

## Prometheus Metrics

**Added:** 2025-01-10
**Status:** Parked
**Category:** DevOps
**Phase:** 2

### Concept

Export metrics for agent pool health, task throughput, cost tracking, and failure rates.

### Use Cases

- Dashboard for agent swarm health
- Alerting on failure rates
- Cost monitoring per repo/team

### Open Questions

- [ ] Which metrics are most valuable?
- [ ] Grafana dashboards or custom UI?
- [ ] Per-agent vs aggregate metrics?

---

## E2B/Modal Integration

**Added:** 2025-01-10
**Status:** Parked
**Category:** Infrastructure
**Phase:** 4

### Concept

Replace local Docker sandboxes with E2B or Modal for production-grade agent isolation with ~150ms cold starts.

### Use Cases

- Production deployment without managing containers
- Auto-scaling based on queue depth
- Better isolation for untrusted code

### Open Questions

- [ ] E2B vs Modal - which fits better?
- [ ] Cost comparison with self-hosted
- [ ] Startup time impact on UX?

---
