import { useCallback, useEffect, useState } from "react";
import {
  createProviderSnapshot,
  deleteSnapshot,
  getSnapshot,
  getSnapshots,
  rollbackSnapshot,
} from "../api";
import { ErrorMessage, Icon, LoadingValue } from "./ui";
import { LocalizedTree } from "../localization";
import type { ApiError, SnapshotDetail, SnapshotSummary } from "../types";

function toApiError(error: unknown): ApiError {
  return error instanceof Error ? error : new Error(String(error));
}

function formatTime(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function size(value: number | undefined) {
  return typeof value === "number" ? `${value} B` : "—";
}

export function BackupRecoveryPage() {
  const [snapshots, setSnapshots] = useState<SnapshotSummary[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [detail, setDetail] = useState<SnapshotDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [message, setMessage] = useState("");
  const [deleteConfirm, setDeleteConfirm] = useState(false);
  const [restoreConfirm, setRestoreConfirm] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const rows = await getSnapshots();
      setSnapshots(rows);
      setSelectedId((current) =>
        rows.some((item) => String(item.id) === current) ? current : "",
      );
    } catch (loadError) {
      setError(toApiError(loadError));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    let active = true;
    void getSnapshot(Number(selectedId)).then(
      (result) => {
        if (active) setDetail(result);
      },
      (loadError: unknown) => {
        if (active) setError(toApiError(loadError));
      },
    );
    return () => {
      active = false;
    };
  }, [selectedId]);

  const capture = async () => {
    setBusy(true);
    setMessage("");
    setError(null);
    try {
      const result = await createProviderSnapshot();
      setMessage(`Captured provider configuration snapshot #${result.id} (${result.rules} rules).`);
      await load();
      setSelectedId(String(result.id));
    } catch (captureError) {
      setError(toApiError(captureError));
    } finally {
      setBusy(false);
    }
  };

  const restore = async () => {
    if (!selectedId || !restoreConfirm) return;
    setBusy(true);
    setMessage("");
    setError(null);
    try {
      const result = await rollbackSnapshot(Number(selectedId), true);
      setMessage(String(result.status ?? "Snapshot restored."));
      setRestoreConfirm(false);
      await load();
    } catch (restoreError) {
      setError(toApiError(restoreError));
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!selectedId || !deleteConfirm) return;
    setBusy(true);
    setMessage("");
    setError(null);
    try {
      await deleteSnapshot(Number(selectedId));
      setMessage(`Snapshot #${selectedId} was deleted from local history.`);
      setDeleteConfirm(false);
      setSelectedId("");
      await load();
    } catch (deleteError) {
      setError(toApiError(deleteError));
    } finally {
      setBusy(false);
    }
  };

  const download = () => {
    if (!detail) return;
    const blob = new Blob([JSON.stringify(detail.state ?? {}, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `netra-snapshot-${detail.id}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  return (
    <LocalizedTree>
      <section className="backup-page">
        <div className="page-heading">
          <div>
            <div className="eyebrow"><span className="eyebrow-line" /> BACKUP &amp; RECOVERY</div>
            <h1>Configuration <span>backups.</span></h1>
            <p className="page-description">
              Capture, verify, download and restore provider configuration snapshots. Database backups are not implemented here.
            </p>
          </div>
          <button className="primary-button" type="button" onClick={() => void capture()} disabled={busy}>
            <Icon name="lock" size={16} />
            {busy ? "Working…" : "Create provider snapshot"}
          </button>
        </div>

        <div className="backup-scope-note">
          <Icon name="alert" size={16} />
          <span>
            These are provider configuration snapshots (user rules), not full database backups. Restore requires explicit confirmation and a configured provider.
          </span>
        </div>

        {error && <div className="panel-state error-state"><ErrorMessage error={error} /></div>}
        {message && <div className="panel-state success-state" role="status">{message}</div>}
        {loading && <div className="panel-state"><LoadingValue /><span>Loading snapshots…</span></div>}

        {!loading && snapshots.length === 0 && (
          <div className="empty-state">
            <span className="empty-icon"><Icon name="lock" size={21} /></span>
            <strong>No configuration snapshots</strong>
            <span>Create a snapshot to capture the provider's current user rules.</span>
          </div>
        )}

        {!loading && snapshots.length > 0 && (
          <div className="backup-layout">
            <aside className="panel">
              <div className="panel-header">
                <div>
                  <div className="panel-kicker">LOCAL HISTORY</div>
                  <h2>Available backups</h2>
                </div>
                <span className="read-only-tag">{snapshots.length} SAVED</span>
              </div>
              <div className="backup-list">
                {snapshots.map((item) => (
                  <button
                    type="button"
                    key={item.id}
                    className={`backup-item${String(item.id) === selectedId ? " selected" : ""}`}
                    onClick={() => setSelectedId(String(item.id))}
                  >
                    <strong>Snapshot #{item.id}</strong>
                    <span>{formatTime(item.created_at)}</span>
                    <span>{item.type ?? "configuration"} · {size(item.size_bytes)}</span>
                    <span className="backup-checksum">{item.checksum ?? "no checksum"}</span>
                  </button>
                ))}
              </div>
            </aside>

            <section className="panel">
              <div className="panel-header">
                <div>
                  <div className="panel-kicker">VERIFICATION</div>
                  <h2>{selectedId ? `Snapshot #${selectedId}` : "Select a snapshot"}</h2>
                </div>
                {detail && (
                  <span className={`read-only-tag${detail.integrity_ok ? "" : " unavailable"}`}>
                    {detail.integrity_ok ? "CHECKSUM MATCH" : "CHECKSUM MISMATCH"}
                  </span>
                )}
              </div>
              {!selectedId ? (
                <div className="empty-state">
                  <span className="empty-icon"><Icon name="lock" size={21} /></span>
                  <strong>No snapshot selected</strong>
                  <span>Choose a saved snapshot to inspect and verify it.</span>
                </div>
              ) : !detail ? (
                <div className="panel-state"><LoadingValue /><span>Verifying snapshot…</span></div>
              ) : (
                <>
                  <div className="dashboard-fact-list">
                    <div><span>Type</span><strong>{detail.type ?? "provider_configuration"}</strong></div>
                    <div><span>Backend</span><strong>{detail.backend ?? "unknown"}</strong></div>
                    <div><span>Size</span><strong>{size(detail.size_bytes)}</strong></div>
                    <div><span>Integrity</span><strong>{detail.integrity_ok ? "Verified" : "Failed"}</strong></div>
                  </div>
                  <details className="backup-state">
                    <summary>Saved state</summary>
                    <pre>{JSON.stringify(detail.state, null, 2)}</pre>
                  </details>
                  <div className="backup-actions">
                    <button className="secondary-button" type="button" onClick={download}>Download JSON</button>
                    <label>
                      <input type="checkbox" checked={restoreConfirm} onChange={(event) => setRestoreConfirm(event.target.checked)} />
                      I confirm restoring this provider configuration.
                    </label>
                    <button className="primary-button" type="button" onClick={() => void restore()} disabled={!restoreConfirm || busy || !detail.integrity_ok}>
                      Restore
                    </button>
                    <label>
                      <input type="checkbox" checked={deleteConfirm} onChange={(event) => setDeleteConfirm(event.target.checked)} />
                      I confirm deleting this local snapshot.
                    </label>
                    <button className="danger-button" type="button" onClick={() => void remove()} disabled={!deleteConfirm || busy}>
                      Delete
                    </button>
                  </div>
                </>
              )}
            </section>
          </div>
        )}

        <section className="panel backup-db-panel">
          <div className="panel-header">
            <div>
              <div className="panel-kicker">NOT IMPLEMENTED</div>
              <h2>Database backups</h2>
            </div>
            <span className="read-only-tag unavailable">UNAVAILABLE</span>
          </div>
          <p>
            Netra does not currently create or restore full database backups. Do not treat configuration snapshots as database backups.
          </p>
        </section>
      </section>
    </LocalizedTree>
  );
}
