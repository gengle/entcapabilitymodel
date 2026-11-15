import { useState } from "react";
import { href, useModel } from "./model";
import type { Cap, Status } from "./types";

const coverageLabels: Record<Exclude<Status, null>, string> = {
  ok: "Covered",
  white: "White space",
  overlap: "Overlap",
};

function CapabilityItems({ caps, depth, showCoverage }: { caps: Cap[]; depth: number; showCoverage: boolean }) {
  return (
    <ul className="map-items">
      {caps.map((cap) => (
        <li key={cap.id}>
          <div className="map-item">
            <a href={href(cap.id)}>{cap.name}</a>
            {showCoverage && cap.status && <span className={`map-status map-status-${cap.status}`}>{coverageLabels[cap.status]}</span>}
          </div>
          {cap.level < depth && cap.children.length > 0 && (
            <CapabilityItems caps={cap.children} depth={depth} showCoverage={showCoverage} />
          )}
        </li>
      ))}
    </ul>
  );
}

export function PrintView() {
  const { snap, dirty } = useModel();
  const treeDepth = (caps: Cap[]): number => caps.reduce((max, cap) => Math.max(max, cap.level, treeDepth(cap.children)), 0);
  const configuredDepth = Object.keys(snap.schema.levels).map(Number).filter((n) => Number.isInteger(n) && n > 0);
  const maxLevel = Math.max(1, treeDepth(snap.capabilities), ...configuredDepth);
  const levels = Array.from({ length: maxLevel }, (_, index) => index + 1);
  const [selectedDepth, setSelectedDepth] = useState(Math.min(3, maxLevel));
  const [domain, setDomain] = useState("");
  const [showCoverage, setShowCoverage] = useState(false);
  const depth = Math.min(selectedDepth, maxLevel);
  const selectedDomain = snap.capabilities.find((cap) => cap.id === domain);
  const domains = selectedDomain ? [selectedDomain] : snap.capabilities;

  return (
    <div className="capability-map">
      <div className="map-toolbar">
        <div>
          <h1>Capability map</h1>
          <p>Explore the enterprise at a glance, then print or save as PDF.</p>
        </div>
        <div className="map-controls">
          <label>
            Domain
            <select value={selectedDomain ? domain : ""} onChange={(event) => setDomain(event.target.value)}>
              <option value="">All domains</option>
              {snap.capabilities.map((cap) => <option key={cap.id} value={cap.id}>{cap.name}</option>)}
            </select>
          </label>
          <label>
            Detail
            <select value={depth} onChange={(event) => setSelectedDepth(Number(event.target.value))}>
              {levels.map((level) => <option key={level} value={level}>L{level} · {snap.schema.levels[level] ?? "Level"}</option>)}
            </select>
          </label>
          <label className="map-coverage-toggle">
            <input type="checkbox" checked={showCoverage} onChange={(event) => setShowCoverage(event.target.checked)} />
            Show coverage
          </label>
          <button className="primary" onClick={() => window.print()}>Print / Save PDF</button>
        </div>
      </div>
      <article className="map-document">
        <header className="map-header">
          <div>
            <div className="map-eyebrow">Enterprise architecture / Capability map</div>
            <h2>{snap.model.name ?? "Semantic model"}</h2>
            <p>{selectedDomain?.name ?? "Enterprise-wide view"} · Through L{depth}</p>
          </div>
          <div className="map-meta">
            <span>MODEL VERSION</span>
            <strong>{snap.model.version ?? "Not specified"}</strong>
          </div>
        </header>
        {dirty.size > 0 && <p className="map-draft">Unsaved edits are present. Verify the live preview before printing.</p>}
        {showCoverage && (
          <p className="map-legend">Coverage: <span>Covered</span> · <span>White space</span> · <span>Overlap</span>.
            Status is shown only for capabilities at L{snap.coverage.minLevel} and below.</p>
        )}
        {domains.length ? (
          <div className="map-domains">
            {domains.map((cap) => (
              <section className="map-domain" key={cap.id}>
                <h3><span className="map-level">L1</span><a href={href(cap.id)}>{cap.name}</a>
                  {showCoverage && cap.status && <span className={`map-status map-status-${cap.status}`}>{coverageLabels[cap.status]}</span>}
                </h3>
                {depth > 1 && cap.children.length > 0 && (
                  <div className="map-groups">
                    {cap.children.map((group) => (
                      <section className="map-group" key={group.id}>
                        <h4><a href={href(group.id)}>{group.name}</a>
                          {showCoverage && group.status && <span className={`map-status map-status-${group.status}`}>{coverageLabels[group.status]}</span>}
                        </h4>
                        {depth > 2 && group.children.length > 0 && (
                          <CapabilityItems caps={group.children} depth={depth} showCoverage={showCoverage} />
                        )}
                      </section>
                    ))}
                  </div>
                )}
              </section>
            ))}
          </div>
        ) : <p className="map-empty">No capabilities to display.</p>}
      </article>
    </div>
  );
}
