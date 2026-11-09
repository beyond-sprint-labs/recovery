import React, { useEffect, useRef, useState, useCallback } from 'react';
import { AgGridReact } from 'ag-grid-react';
import {
  AllCommunityModule,
  ModuleRegistry,
  themeQuartz,
} from 'ag-grid-community';
import type {
  GridReadyEvent,
  GridApi,
  RowClassRules,
} from 'ag-grid-community';

import type { AuditEvent } from '../types/api';
import { auditColDefs } from '../grid/auditColumns';
import { apiClient } from '../api/client';
import { Play, Pause, RefreshCw } from 'lucide-react';

// Register AG Grid Community modules
ModuleRegistry.registerModules([AllCommunityModule]);

export const AuditPage: React.FC = () => {
  const [gridApi, setGridApi] = useState<GridApi<AuditEvent> | null>(null);
  const [isStreaming, setIsStreaming] = useState(true);
  const [lastSeq, setLastSeq] = useState(0);
  const [eventCount, setEventCount] = useState(0);
  const [blockedAlertCount, setBlockedAlertCount] = useState(0);
  const pollingTimerRef = useRef<number | null>(null);

  const getRowId = useCallback((params: { data: AuditEvent }) => params.data.event_id, []);

  // Row class rules for intense red highlight on PROPOSAL_BLOCKED (DoD requirement)
  const rowClassRules: RowClassRules<AuditEvent> = {
    'row-blocked-critical': (params) => {
      return (
        params.data?.action === 'PROPOSAL_BLOCKED' ||
        params.data?.severity === 'CRITICAL' ||
        params.data?.state_to === 'BLOCKED'
      );
    },
    'row-payment-success': (params) => {
      return params.data?.action === 'PAYMENT_CONFIRMED' || params.data?.state_to === 'PAID';
    },
  };

  const onGridReady = useCallback((params: GridReadyEvent<AuditEvent>) => {
    setGridApi(params.api);
  }, []);

  // Poll audit events and apply incremental transaction
  const pollEvents = useCallback(async () => {
    if (!gridApi) return;
    try {
      const newEvents = await apiClient.getAuditEvents(lastSeq);
      if (newEvents && newEvents.length > 0) {
        const maxSeq = Math.max(...newEvents.map((e) => e.seq), lastSeq);
        setLastSeq(maxSeq);

        const addedRows: AuditEvent[] = [];
        let newBlockedCount = 0;

        for (const evt of newEvents) {
          const existingNode = gridApi.getRowNode(evt.event_id);
          if (!existingNode) {
            addedRows.push(evt);
            if (evt.action === 'PROPOSAL_BLOCKED' || evt.severity === 'CRITICAL') {
              newBlockedCount++;
            }
          }
        }

        if (addedRows.length > 0) {
          gridApi.applyTransaction({ add: addedRows, addIndex: 0 });
          setEventCount((prev) => prev + addedRows.length);
          if (newBlockedCount > 0) {
            setBlockedAlertCount((prev) => prev + newBlockedCount);
          }

          // Flash newly inserted cells
          const rowNodesToFlash = addedRows
            .map((r) => gridApi.getRowNode(r.event_id))
            .filter(Boolean);
          if (rowNodesToFlash.length > 0) {
            gridApi.flashCells({ rowNodes: rowNodesToFlash as any });
          }
        }
      }
    } catch (err) {
      console.error('Error polling audit stream:', err);
    }
  }, [gridApi, lastSeq]);

  useEffect(() => {
    if (!gridApi) return;

    pollEvents();

    if (isStreaming) {
      pollingTimerRef.current = window.setInterval(pollEvents, 2000);
    }

    return () => {
      if (pollingTimerRef.current) clearInterval(pollingTimerRef.current);
    };
  }, [gridApi, isStreaming, pollEvents]);

  const handleResetStream = () => {
    apiClient.resetMockStream();
    if (gridApi) {
      gridApi.setGridOption('rowData', []);
    }
    setLastSeq(0);
    setEventCount(0);
    setBlockedAlertCount(0);
    pollEvents();
  };

  return (
    <div className="page-container">
      <div className="page-header">
        <div>
          <h2>Live Audit & Compliance Trail</h2>
          <p className="subtitle">
            Immutable AG Grid event stream monitoring financial policy guardrails, state transitions, and PayPal orchestration.
          </p>
        </div>

        <div className="header-actions">
          <button
            className={`btn ${isStreaming ? 'btn-warning' : 'btn-primary'}`}
            onClick={() => setIsStreaming(!isStreaming)}
            aria-label={isStreaming ? 'Pause live audit stream' : 'Resume live audit stream'}
          >
            {isStreaming ? (
              <>
                <Pause size={15} /> Pause Stream
              </>
            ) : (
              <>
                <Play size={15} /> Resume Stream
              </>
            )}
          </button>
          <button
            className="btn btn-secondary"
            onClick={handleResetStream}
            aria-label="Reset audit stream to initial seed"
          >
            <RefreshCw size={15} /> Reset Stream
          </button>
        </div>
      </div>

      <div className="stats-bar">
        <div className="stat-card">
          <span className="stat-label">Events Streamed</span>
          <span className="stat-value">{eventCount}</span>
        </div>
        <div className="stat-card stat-critical">
          <span className="stat-label">Guardrail Interceptions</span>
          <span className="stat-value">{blockedAlertCount}</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">Polling Interval</span>
          <span className="stat-value">2.0s</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">Grid Engine</span>
          <span className="stat-value">AG Grid Community</span>
        </div>
      </div>

      <div className="grid-wrapper">
        <AgGridReact<AuditEvent>
          theme={themeQuartz}
          columnDefs={auditColDefs}
          getRowId={getRowId}
          rowClassRules={rowClassRules}
          onGridReady={onGridReady}
          pagination={false}
          enableCellTextSelection={true}
          defaultColDef={{
            sortable: true,
            filter: true,
            resizable: true,
          }}
        />
      </div>
    </div>
  );
};
