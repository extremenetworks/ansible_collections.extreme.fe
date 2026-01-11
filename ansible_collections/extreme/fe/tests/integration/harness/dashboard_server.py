#!/usr/bin/env python3
"""Serve the Extreme FE dashboard over WebSockets using FastAPI."""
from __future__ import annotations

import asyncio
import asyncio.subprocess
import datetime as _dt
import html
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Literal, Optional, Sequence
from urllib.parse import urlparse, unquote

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, status
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
import uvicorn

INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8" />
    <title>Extreme FE Dashboard</title>
    <style>
        :root {
            color-scheme: dark;
        }
        * {
            box-sizing: border-box;
        }
        body {
            margin: 0;
            font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
            background: #0f172a;
            color: #e2e8f0;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
        }
        header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 1.5rem;
            padding: 1.25rem 1.75rem;
            border-bottom: 1px solid rgba(148, 163, 184, 0.25);
            background: rgba(15, 23, 42, 0.9);
        }
        .header-left {
            display: flex;
            flex-direction: column;
            gap: 0.75rem;
        }
        header h1 {
            margin: 0;
            font-size: 1.4rem;
            letter-spacing: 0.02em;
        }
        .control-bar {
            display: flex;
            align-items: center;
            gap: 1rem;
            flex-wrap: wrap;
        }
        .status-indicator {
            min-width: 70px;
            padding: 0.35rem 0.85rem;
            border-radius: 999px;
            text-align: center;
            font-weight: 600;
            letter-spacing: 0.07em;
            text-transform: uppercase;
            border: 1px solid rgba(148, 163, 184, 0.35);
            background: rgba(148, 163, 184, 0.15);
            color: #e2e8f0;
        }
        .status-pass {
            color: #34d399;
            border-color: rgba(52, 211, 153, 0.5);
            background: rgba(52, 211, 153, 0.18);
        }
        .status-fail {
            color: #f87171;
            border-color: rgba(248, 113, 113, 0.5);
            background: rgba(248, 113, 113, 0.18);
        }
        .status-run {
            color: #fbbf24;
            border-color: rgba(251, 191, 36, 0.6);
            background: rgba(251, 191, 36, 0.18);
        }
        .status-na {
            color: #fbbf24;
            border-color: rgba(251, 191, 36, 0.5);
            background: rgba(251, 191, 36, 0.15);
        }
        .control-button {
            padding: 0.55rem 1.35rem;
            border-radius: 999px;
            border: 1px solid rgba(52, 211, 153, 0.5);
            background: rgba(52, 211, 153, 0.18);
            color: #34d399;
            font-weight: 600;
            letter-spacing: 0.05em;
            cursor: pointer;
            transition: filter 0.2s ease, transform 0.1s ease;
        }
        .control-button:disabled {
            opacity: 0.6;
            cursor: not-allowed;
        }
        .control-button:hover:not(:disabled) {
            filter: brightness(1.05);
        }
        .control-button:active:not(:disabled) {
            transform: translateY(1px);
        }
        .control-start {
            border-color: rgba(52, 211, 153, 0.5);
            background: rgba(52, 211, 153, 0.18);
            color: #34d399;
        }
        .control-cancel {
            border-color: rgba(248, 113, 113, 0.5);
            background: rgba(248, 113, 113, 0.18);
            color: #f87171;
        }
        .control-config {
            border-color: rgba(96, 165, 250, 0.5);
            background: rgba(96, 165, 250, 0.18);
            color: #60a5fa;
        }
        .control-coverage {
            border-color: rgba(250, 204, 21, 0.55);
            background: rgba(250, 204, 21, 0.18);
            color: #facc15;
        }
        .control-topology {
            border-color: rgba(14, 165, 233, 0.5);
            background: rgba(14, 165, 233, 0.2);
            color: #67e8f9;
        }
        .control-docs {
            border-color: rgba(168, 85, 247, 0.5);
            background: rgba(168, 85, 247, 0.18);
            color: #c084fc;
        }
        .connection-status {
            font-size: 0.85rem;
            letter-spacing: 0.04em;
            text-transform: uppercase;
            padding: 0.45rem 1rem;
            border-radius: 999px;
            border: 1px solid rgba(148, 163, 184, 0.3);
            align-self: flex-end;
        }
        .connection-waiting {
            color: #fbbf24;
            border-color: rgba(251, 191, 36, 0.6);
            background: rgba(251, 191, 36, 0.12);
        }
        .connection-ok {
            color: #34d399;
            border-color: rgba(52, 211, 153, 0.5);
            background: rgba(52, 211, 153, 0.18);
        }
        .connection-error {
            color: #f87171;
            border-color: rgba(248, 113, 113, 0.5);
            background: rgba(248, 113, 113, 0.18);
        }
        .header-right {
            display: flex;
            flex-direction: column;
            align-items: flex-end;
            gap: 0.75rem;
        }
        .host-status-list {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, max-content));
            gap: 0.45rem;
            justify-content: flex-end;
            align-content: flex-start;
            justify-items: end;
        }
        .host-status-badge {
            padding: 0.3rem 0.75rem;
            font-size: 0.8rem;
        .host-status-badge:hover {
            filter: brightness(1.05);
        }
            letter-spacing: 0.04em;
            border: 1px solid rgba(148, 163, 184, 0.35);
            background: rgba(15, 23, 42, 0.5);
            color: #cbd5f5;
            white-space: nowrap;
            cursor: pointer;
        }
        .host-status-badge:focus-visible {
            outline: 2px solid rgba(250, 204, 21, 0.75);
            outline-offset: 2px;
        }
        .host-status-up {
            border-color: rgba(250, 204, 21, 0.55);
            background: rgba(250, 204, 21, 0.18);
            color: #facc15;
        }
        .host-status-down {
            border-color: rgba(248, 113, 113, 0.45);
            background: rgba(248, 113, 113, 0.18);
            color: #f87171;
        }
        main {
            flex: 1;
            padding: 1.5rem;
            display: flex;
            flex-direction: column;
        }
        .config-panel {
            margin-bottom: 1.5rem;
            padding: 1.5rem;
            border-radius: 16px;
            border: 1px solid rgba(148, 163, 184, 0.25);
            background: rgba(15, 23, 42, 0.65);
            box-shadow: 0 18px 45px rgba(15, 23, 42, 0.35);
        }
        .docs-panel {
            margin-bottom: 1.5rem;
            padding: 1.5rem;
            border-radius: 16px;
            border: 1px solid rgba(168, 85, 247, 0.3);
            background: rgba(76, 29, 149, 0.35);
            box-shadow: 0 18px 45px rgba(76, 29, 149, 0.25);
        }
        .config-header {
            margin: 0 0 1rem;
            font-size: 1.1rem;
            font-weight: 600;
            letter-spacing: 0.02em;
        }
        .docs-header {
            margin: 0 0 1rem;
            font-size: 1.1rem;
            font-weight: 600;
            letter-spacing: 0.02em;
        }
        .config-list {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
            gap: 0.75rem 1rem;
        }
        .config-entry {
            display: flex;
            align-items: center;
            gap: 0.75rem;
            font-size: 0.95rem;
        }
        .config-entry-label {
            display: flex;
            align-items: center;
            gap: 0.65rem;
            flex: 1;
        }
        .config-entry-label span {
            flex: 1;
        }
        /* Style checkboxes as circular toggles so they read like radio buttons. */
        .config-entry input {
            appearance: none;
            width: 18px;
            height: 18px;
            border-radius: 50%;
            border: 2px solid rgba(148, 163, 184, 0.7);
            background: transparent;
            position: relative;
            cursor: pointer;
            transition: border-color 0.2s ease, background 0.2s ease;
        }
        .config-entry input:focus-visible {
            outline: 2px solid #38bdf8;
            outline-offset: 2px;
        }
        .config-entry input:checked {
            border-color: #38bdf8;
            background: rgba(56, 189, 248, 0.25);
        }
        .config-entry input:checked::after {
            content: "";
            position: absolute;
            top: 3px;
            left: 3px;
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: #38bdf8;
        }
        .config-edit-button {
            padding: 0.4rem 0.9rem;
            border-radius: 999px;
            border: 1px solid rgba(96, 165, 250, 0.5);
            background: rgba(37, 99, 235, 0.2);
            color: #bfdbfe;
            font-weight: 600;
            letter-spacing: 0.04em;
            cursor: pointer;
            transition: filter 0.2s ease;
            white-space: nowrap;
        }
        .config-edit-button:hover:not(:disabled) {
            filter: brightness(1.05);
        }
        .config-edit-button:disabled {
            opacity: 0.6;
            cursor: not-allowed;
        }
        .config-block {
            margin-top: 1rem;
            display: flex;
            flex-direction: column;
            gap: 0.85rem;
            padding: 1.1rem 1.25rem;
            border: 1px solid rgba(148, 163, 184, 0.3);
            border-radius: 14px;
            background: rgba(15, 23, 42, 0.5);
            box-shadow: inset 0 0 0 1px rgba(15, 23, 42, 0.4);
        }
        .config-block:first-of-type {
            margin-top: 0;
        }
        .config-subheader {
            margin: 0;
            font-size: 1rem;
            font-weight: 600;
            letter-spacing: 0.03em;
        }
        .config-options {
            display: flex;
            flex-direction: column;
            gap: 1rem;
        }
        .config-option {
            display: flex;
            align-items: center;
            gap: 1rem;
            flex-wrap: wrap;
        }
        .config-option-title {
            font-size: 0.95rem;
            font-weight: 600;
            color: #cbd5f5;
            min-width: 120px;
        }
        .toggle-group {
            display: flex;
            gap: 0.75rem;
            flex-wrap: wrap;
        }
        .toggle-option {
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.4rem 0.9rem;
            border-radius: 999px;
            border: 1px solid rgba(148, 163, 184, 0.35);
            background: rgba(15, 23, 42, 0.45);
            cursor: pointer;
            user-select: none;
            transition: border-color 0.2s ease, background 0.2s ease;
        }
        .toggle-option input {
            appearance: none;
            width: 14px;
            height: 14px;
            border-radius: 50%;
            border: 2px solid rgba(148, 163, 184, 0.7);
            background: transparent;
            position: relative;
        }
        .toggle-option input:checked {
            border-color: #38bdf8;
            background: rgba(56, 189, 248, 0.25);
        }
        .toggle-option input:checked::after {
            content: "";
            position: absolute;
            top: 2px;
            left: 2px;
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background: #38bdf8;
        }
        .single-toggle {
            position: relative;
            display: inline-flex;
            align-items: center;
            gap: 0.6rem;
            padding: 0.4rem 0.95rem 0.4rem 0.75rem;
            border-radius: 999px;
            border: 1px solid rgba(148, 163, 184, 0.35);
            background: rgba(15, 23, 42, 0.45);
            cursor: pointer;
            user-select: none;
            min-width: 140px;
        }
        .single-toggle input {
            position: absolute;
            inset: 0;
            margin: 0;
            opacity: 0;
            cursor: pointer;
        }
        .single-toggle-visual {
            width: 36px;
            height: 20px;
            border-radius: 999px;
            border: 1px solid rgba(148, 163, 184, 0.6);
            background: rgba(148, 163, 184, 0.35);
            display: inline-flex;
            align-items: center;
            padding: 0 3px;
            transition: background 0.2s ease, border-color 0.2s ease;
        }
        .single-toggle-dot {
            width: 12px;
            height: 12px;
            border-radius: 50%;
            background: #94a3b8;
            transition: transform 0.2s ease, background 0.2s ease;
        }
        .single-toggle input:checked + .single-toggle-visual {
            background: rgba(56, 189, 248, 0.25);
            border-color: #38bdf8;
        }
        .single-toggle input:checked + .single-toggle-visual .single-toggle-dot {
            transform: translateX(14px);
            background: #38bdf8;
        }
        .single-toggle-text {
            font-size: 0.9rem;
            letter-spacing: 0.03em;
            color: #cbd5f5;
            transition: color 0.2s ease;
        }
        .single-toggle input:not(:checked) + .single-toggle-visual + .single-toggle-text {
            color: #94a3b8;
        }
        .config-verbose {
            display: flex;
            gap: 0.5rem;
            flex-wrap: wrap;
        }
        .verbose-option {
            display: inline-flex;
            align-items: center;
            gap: 0.4rem;
            padding: 0.35rem 0.65rem;
            border-radius: 12px;
            border: 1px solid rgba(148, 163, 184, 0.35);
            background: rgba(15, 23, 42, 0.45);
            cursor: pointer;
            user-select: none;
            transition: border-color 0.2s ease, background 0.2s ease;
        }
        .verbose-option input {
            appearance: none;
            width: 14px;
            height: 14px;
            border-radius: 50%;
            border: 2px solid rgba(148, 163, 184, 0.7);
            background: transparent;
            position: relative;
        }
        .verbose-option input:checked {
            border-color: #a855f7;
            background: rgba(168, 85, 247, 0.25);
        }
        .verbose-option input:checked::after {
            content: "";
            position: absolute;
            top: 2px;
            left: 2px;
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background: #a855f7;
        }
        .verbose-option span {
            font-size: 0.85rem;
        }
        .config-empty {
            color: #94a3b8;
            font-style: italic;
        }
        .config-bulk-actions {
            margin-top: 1rem;
            display: flex;
            gap: 0.75rem;
            flex-wrap: wrap;
            justify-content: flex-start;
        }
        .docs-list {
            display: flex;
            flex-direction: column;
            gap: 0.85rem;
        }
        .docs-entry {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 1rem;
            padding: 0.85rem 1rem;
            border-radius: 12px;
            background: rgba(30, 41, 59, 0.65);
            border: 1px solid rgba(168, 85, 247, 0.25);
        }
        .docs-name {
            font-weight: 600;
            letter-spacing: 0.03em;
            flex: 1;
        }
        .docs-buttons {
            display: flex;
            gap: 0.65rem;
        }
        .docs-button {
            padding: 0.4rem 0.9rem;
            border-radius: 999px;
            border: 1px solid rgba(168, 85, 247, 0.45);
            background: rgba(168, 85, 247, 0.18);
            color: #f5d0fe;
            font-weight: 600;
            letter-spacing: 0.05em;
            cursor: pointer;
            transition: filter 0.2s ease;
        }
        .docs-button:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }
        .docs-button:hover:not(:disabled) {
            filter: brightness(1.05);
        }
        .docs-empty {
            color: #d8b4fe;
            font-style: italic;
        }
        .docs-actions {
            margin-top: 1.25rem;
            display: flex;
            justify-content: flex-start;
        }
        .config-panel[hidden] {
            display: none;
        }
        .docs-panel[hidden] {
            display: none;
        }
        iframe {
            flex: 1;
            width: 100%;
            border: none;
            border-radius: 16px;
            background: rgba(15, 23, 42, 0.65);
            box-shadow: 0 18px 45px rgba(15, 23, 42, 0.45);
        }
        .placeholder {
            margin: 0 auto;
            margin-top: 2.5rem;
            max-width: 520px;
            padding: 1.75rem;
            border-radius: 16px;
            text-align: center;
            background: rgba(148, 163, 184, 0.1);
            border: 1px dashed rgba(148, 163, 184, 0.25);
            line-height: 1.6;
        }
        footer {
            padding: 0.9rem 1.75rem;
            font-size: 0.85rem;
            color: #94a3b8;
            border-top: 1px solid rgba(148, 163, 184, 0.25);
            background: rgba(15, 23, 42, 0.75);
        }
        @media (max-width: 768px) {
            header {
                flex-direction: column;
                align-items: flex-start;
            }
            header, footer {
                padding: 1rem;
            }
            main {
                padding: 1rem;
            }
            .config-panel {
                padding: 1.25rem;
            }
            .docs-panel {
                padding: 1.25rem;
            }
            .header-right {
                width: 100%;
                align-items: flex-start;
            }
            .host-status-list {
                grid-template-columns: repeat(2, minmax(0, max-content));
                justify-content: flex-start;
                justify-items: start;
            }
            .header-right .connection-status {
                align-self: flex-start;
            }
        }
    </style>
</head>
<body>
    <header>
        <div class="header-left">
            <h1>Extreme FE Dashboard</h1>
            <div class="control-bar">
                <button id="control-button" class="control-button control-start">Start</button>
                <div id="run-status" class="status-indicator status-na">N/A</div>
                <button id="docs-button" class="control-button control-docs">Docs</button>
                <button id="topology-button" class="control-button control-topology">Topology</button>
                <button id="config-button" class="control-button control-config">Config</button>
                <button id="coverage-button" class="control-button control-coverage" hidden>Code Coverage</button>
            </div>
        </div>
        <div class="header-right">
            <div id="connection-status" class="connection-status connection-waiting">Connecting…</div>
            <div id="host-status-list" class="host-status-list" hidden></div>
        </div>
    </header>
    <main>
        <section id="config-panel" class="config-panel" hidden>
            <h2 class="config-header">Configure Test Run</h2>
            <div class="config-block">
                <h3 class="config-subheader">Test Files</h3>
                <div id="config-list" class="config-list"></div>
                <div class="config-bulk-actions">
                    <button id="config-clear" class="control-button control-config" disabled>Clear</button>
                    <button id="config-select-all" class="control-button control-config" disabled>Select All</button>
                </div>
            </div>
            <div class="config-block">
                <h3 class="config-subheader">Run Options</h3>
                <div id="config-settings" class="config-options"></div>
            </div>
        </section>
        <section id="docs-panel" class="docs-panel" hidden>
            <h2 class="docs-header">Documentation</h2>
            <div id="docs-list" class="docs-list"></div>
            <div class="docs-actions">
                <button id="docs-back" class="control-button control-docs">Back</button>
            </div>
        </section>
        <div id="placeholder" class="placeholder">
            Waiting for <code>run_test.py</code> to publish dashboard updates…
        </div>
        <iframe id="dashboard-frame" title="Dashboard view" hidden></iframe>
    </main>
    <footer>
        WebSocket endpoint: <code>ws://&lt;host&gt;:4000/ws</code>
    </footer>
    <script>
    (function () {
        'use strict';

        const frame = document.getElementById('dashboard-frame');
        const placeholder = document.getElementById('placeholder');
        const connectionStatus = document.getElementById('connection-status');
        const controlButton = document.getElementById('control-button');
        const statusIndicator = document.getElementById('run-status');
        const configButton = document.getElementById('config-button');
        const docsButton = document.getElementById('docs-button');
        const topologyButton = document.getElementById('topology-button');
        const coverageButton = document.getElementById('coverage-button');
        const hostStatusList = document.getElementById('host-status-list');
        const configPanel = document.getElementById('config-panel');
        const configList = document.getElementById('config-list');
        const configSettingsContainer = document.getElementById('config-settings');
        const configClearButton = document.getElementById('config-clear');
        const configSelectAllButton = document.getElementById('config-select-all');
        const docsPanel = document.getElementById('docs-panel');
        const docsList = document.getElementById('docs-list');
        const docsBackButton = document.getElementById('docs-back');
        const reconnectDelay = 3000;
        const defaultSummary = 'test.yml';
        let socket = null;
        let reconnectTimer = null;
        let configEntries = [];
        let inventoryOptions = [];
        let configSettings = {
            testCoverage: false,
            traceHttp: false,
            verboseLevel: 0,
            diff: false,
            gns3Server: true,
            inventory: ''
        };
        updateTopologyButtonVisibility(configSettings.gns3Server);
        let configUpdateTimer = null;
        let configUpdateInProgress = false;
        let configUpdateQueued = false;
        let coverageUrl = null;
        let hostStatuses = [];
        let runState = {
            running: false,
            summary: defaultSummary,
            returncode: null,
            status: 'na'
        };

        function requestHostShell(host) {
            if (typeof host !== 'string' || !host.trim()) {
                return;
            }
            const payload = { host: host.trim() };
            fetch('/host/shell', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            }).then((response) => {
                if (response.ok) {
                    return;
                }
                return response
                    .json()
                    .catch(() => ({ detail: response.statusText || 'Unknown error' }))
                    .then((data) => {
                        const detail = data && typeof data.detail === 'string' ? data.detail : 'Unknown error';
                        throw new Error(detail);
                    });
            }).catch((error) => {
                console.error('Failed to launch host shell', error);
                alert('Failed to open host terminal: ' + (error && error.message ? error.message : error));
            });
        }

        function normalizeRunStatus(value) {
            if (typeof value !== 'string') {
                return 'na';
            }
            const normalized = value.toLowerCase();
            if (normalized === 'pass' || normalized === 'fail' || normalized === 'run' || normalized === 'na') {
                return normalized;
            }
            return 'na';
        }

        function setConnectionStatus(text, cssClass) {
            connectionStatus.textContent = text;
            connectionStatus.className = 'connection-status ' + cssClass;
        }

        function determineStatus() {
            if (typeof runState.returncode === 'number') {
                return runState.returncode === 0 ? 'pass' : 'fail';
            }
            const currentStatus = normalizeRunStatus(runState.status);
            if (currentStatus === 'pass' || currentStatus === 'fail') {
                return currentStatus;
            }
            if (runState.running) {
                return currentStatus === 'na' ? 'run' : currentStatus;
            }
            if (currentStatus === 'run') {
                return 'na';
            }
            return currentStatus;
        }

        function escapeHtml(value) {
            return String(value ?? '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#39;');
        }

        function applyStatusIndicator(status) {
            if (!statusIndicator) {
                return;
            }
            const classes = ['status-indicator'];
            if (status === 'pass') {
                classes.push('status-pass');
                statusIndicator.textContent = 'PASS';
            } else if (status === 'fail') {
                classes.push('status-fail');
                statusIndicator.textContent = 'FAIL';
            } else if (status === 'run') {
                classes.push('status-run');
                statusIndicator.textContent = 'RUN';
            } else {
                classes.push('status-na');
                statusIndicator.textContent = 'N/A';
            }
            statusIndicator.className = classes.join(' ');
        }

        function updateStatusIndicator() {
            const status = determineStatus();
            applyStatusIndicator(status);
        }

        function updateCoverageButtonState(url) {
            coverageUrl = typeof url === 'string' && url.trim().length ? url.trim() : null;
            if (!coverageButton) {
                return;
            }
            if (coverageUrl) {
                coverageButton.hidden = false;
                coverageButton.disabled = false;
                coverageButton.title = coverageUrl;
            } else {
                coverageButton.hidden = true;
                coverageButton.disabled = true;
                coverageButton.title = 'Code coverage report not available';
            }
        }

        function updateTopologyButtonVisibility(enabled) {
            if (!topologyButton) {
                return;
            }
            const shouldShow = Boolean(enabled);
            topologyButton.hidden = !shouldShow;
            topologyButton.setAttribute('aria-hidden', shouldShow ? 'false' : 'true');
            topologyButton.disabled = !shouldShow;
        }

        function resolveCoverageTarget(rawUrl) {
            if (!rawUrl) {
                return null;
            }
            let target = rawUrl.trim();
            if (!target) {
                return null;
            }
            try {
                const parsed = new URL(target, window.location.origin);
                if (parsed.protocol !== 'file:' || target.startsWith('file:')) {
                    return parsed.href;
                }
            } catch (_) {
                // Fall through to path handling below.
            }
            const hasScheme = /^[a-z][a-z0-9+.-]*:/i.test(target);
            if (hasScheme) {
                return target;
            }
            const normalized = target.split('\\\\').join('/');
            if (/^[a-z]:/i.test(target)) {
                return `file:///${normalized}`;
            }
            if (normalized.startsWith('//')) {
                return `file:${normalized}`;
            }
            if (normalized.startsWith('/')) {
                return `file://${normalized}`;
            }
            return `file:///${normalized}`;
        }

        function isConfigPanelVisible() {
            return !configPanel.hidden;
        }

        function hideConfigPanel() {
            configPanel.hidden = true;
        }

        function isDocsPanelVisible() {
            return !docsPanel.hidden;
        }

        function hideDocsPanel() {
            docsPanel.hidden = true;
        }

        function getScrollPosition() {
            try {
                if (frame.contentWindow) {
                    return frame.contentWindow.scrollY;
                }
                const doc = frame.contentDocument;
                if (!doc) {
                    return 0;
                }
                return doc.documentElement?.scrollTop || doc.body?.scrollTop || 0;
            } catch (_) {
                return 0;
            }
        }

        function restoreScrollPosition(position) {
            try {
                if (frame.contentWindow) {
                    frame.contentWindow.scrollTo(0, position);
                    return;
                }
                const doc = frame.contentDocument;
                if (doc?.documentElement) {
                    doc.documentElement.scrollTop = position;
                }
                if (doc?.body) {
                    doc.body.scrollTop = position;
                }
            } catch (_) {
                // Ignore scroll restoration failures.
            }
        }

        function hideStatusBadge() {
            try {
                const doc = frame.contentDocument;
                if (!doc) {
                    return;
                }
                const badge = doc.querySelector('.status-badge');
                if (badge) {
                    badge.style.display = 'none';
                }
            } catch (_) {
                // ignore
            }
        }

        function applyContent(html) {
            if (!html) {
                frame.hidden = true;
                placeholder.hidden = false;
                return;
            }
            const previousScroll = frame.hidden ? 0 : getScrollPosition();
            placeholder.hidden = true;
            frame.hidden = false;
            const doc = frame.contentDocument;
            if (doc) {
                doc.open();
                doc.write(html);
                doc.close();
            } else {
                frame.srcdoc = html;
            }
            let attempts = 0;
            const maxAttempts = 6;
            const tryRestore = () => {
                attempts += 1;
                hideStatusBadge();
                restoreScrollPosition(previousScroll);
                if (attempts < maxAttempts) {
                    window.requestAnimationFrame(tryRestore);
                }
            };
            window.requestAnimationFrame(tryRestore);
        }

        async function fetchLatest() {
            try {
                const response = await fetch('/latest', { cache: 'no-store' });
                if (!response.ok) {
                    throw new Error('HTTP ' + response.status);
                }
                const payload = await response.json();
                if (payload && Object.prototype.hasOwnProperty.call(payload, 'content')) {
                    applyContent(payload.content);
                }
            } catch (err) {
                console.error('Failed to fetch latest dashboard', err);
            }
        }

        function mapEntriesFromPayload(entries) {
            if (!Array.isArray(entries)) {
                return [];
            }
            return entries
                .filter((item) => item && typeof item.filename === 'string' && item.filename.length)
                .map((item) => ({
                    filename: item.filename,
                    label: typeof item.label === 'string' && item.label.length ? item.label : item.filename,
                    selected: Boolean(item.selected)
                }));
        }

        function normalizeInventoryOptions(values) {
            if (!Array.isArray(values)) {
                return [];
            }
            const seen = new Set();
            const result = [];
            for (const value of values) {
                if (typeof value !== 'string') {
                    continue;
                }
                const trimmed = value.trim();
                if (!trimmed || seen.has(trimmed)) {
                    continue;
                }
                seen.add(trimmed);
                result.push(trimmed);
            }
            result.sort((a, b) => a.localeCompare(b));
            return result;
        }

        function normalizeHostStatuses(entries) {
            if (!Array.isArray(entries)) {
                return [];
            }
            const seen = new Set();
            const result = [];
            for (const entry of entries) {
                if (!entry || typeof entry.host !== 'string') {
                    continue;
                }
                const host = entry.host.trim();
                if (!host || seen.has(host)) {
                    continue;
                }
                seen.add(host);
                result.push({
                    host,
                    reachable: Boolean(entry.reachable),
                    target: typeof entry.target === 'string' ? entry.target.trim() : ''
                });
            }
            result.sort((a, b) => a.host.localeCompare(b.host));
            return result;
        }

        function renderHostStatuses() {
            if (!hostStatusList) {
                return;
            }
            if (!Array.isArray(hostStatuses) || hostStatuses.length === 0) {
                hostStatusList.innerHTML = '';
                hostStatusList.hidden = true;
                return;
            }
            hostStatusList.hidden = false;
            hostStatusList.innerHTML = '';
            for (const entry of hostStatuses) {
                const badge = document.createElement('div');
                const isUp = Boolean(entry.reachable);
                badge.className = 'host-status-badge ' + (isUp ? 'host-status-up' : 'host-status-down');
                badge.textContent = entry.host;
                if (entry.target) {
                    badge.title = entry.target;
                }
                badge.dataset.host = entry.host;
                badge.setAttribute('role', 'button');
                badge.tabIndex = 0;
                badge.addEventListener('click', () => {
                    requestHostShell(entry.host);
                });
                badge.addEventListener('keydown', (event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault();
                        requestHostShell(entry.host);
                    }
                });
                hostStatusList.appendChild(badge);
            }
        }

        function applyHostStatusUpdate(entries) {
            hostStatuses = Array.isArray(entries) ? entries : [];
            renderHostStatuses();
        }

        function updateSingleToggleLabel(input) {
            if (!input) {
                return;
            }
            const label = input.closest('.single-toggle');
            if (!label) {
                return;
            }
            const textSpan = label.querySelector('.single-toggle-text');
            if (textSpan) {
                textSpan.textContent = input.checked ? 'On' : 'Off';
            }
        }

        function syncSingleToggleLabels() {
            if (!configPanel) {
                return;
            }
            const toggles = configPanel.querySelectorAll('.single-toggle input');
            toggles.forEach((input) => updateSingleToggleLabel(input));
        }

        function normalizeSettings(data) {
            const defaults = {
                testCoverage: false,
                traceHttp: false,
                verboseLevel: 0,
                diff: false,
                gns3Server: true,
                inventory: ''
            };
            if (!data || typeof data !== 'object') {
                return { ...defaults };
            }
            const rawLevel = Number.parseInt(
                data.verbose_level ?? data.verboseLevel ?? defaults.verboseLevel,
                10
            );
            const rawInventory = data.inventory ?? data.inventory_selection ?? defaults.inventory;
            const rawGns3 = data.gns3_server ?? data.gns3Server ?? defaults.gns3Server;
            return {
                testCoverage: Boolean(data.test_coverage ?? data.testCoverage ?? defaults.testCoverage),
                traceHttp: Boolean(data.trace_http ?? data.traceHttp ?? defaults.traceHttp),
                verboseLevel: Number.isNaN(rawLevel)
                    ? defaults.verboseLevel
                    : Math.min(5, Math.max(0, rawLevel)),
                diff: Boolean(data.diff ?? defaults.diff),
                gns3Server: Boolean(rawGns3),
                inventory: typeof rawInventory === 'string' ? rawInventory : defaults.inventory
            };
        }

        function renderSettingsOptions() {
            if (!configSettingsContainer) {
                return;
            }
            const settings = normalizeSettings(configSettings);
            configSettings = settings;
            updateTopologyButtonVisibility(settings.gns3Server);
            const selection = typeof settings.inventory === 'string' ? settings.inventory : '';
            const availableInventories = Array.isArray(inventoryOptions)
                ? inventoryOptions.slice()
                : [];
            if (selection && !availableInventories.includes(selection)) {
                availableInventories.push(selection);
                availableInventories.sort((a, b) => a.localeCompare(b));
            }
            const hasInventories = availableInventories.length > 0;
            const inventorySelectAttributes = hasInventories ? '' : ' disabled';
            let inventoryOptionsMarkup = '';
            if (hasInventories) {
                const placeholderSelected = selection === '';
                const placeholderOption = `<option value=""${placeholderSelected ? ' selected' : ''}>Select inventory...</option>`;
                const optionMarkup = availableInventories
                    .map((name) => {
                        const safe = escapeHtml(name);
                        const isSelected = name === selection ? ' selected' : '';
                        return `<option value="${safe}"${isSelected}>${safe}</option>`;
                    })
                    .join('');
                inventoryOptionsMarkup = placeholderOption + optionMarkup;
            } else {
                inventoryOptionsMarkup = '<option value="">No inventory files found</option>';
            }
            const verboseOptions = Array.from({ length: 6 }, (_, level) => `
                        <label class="verbose-option">
                            <input type="radio" name="verbose-level" value="${level}" ${settings.verboseLevel === level ? 'checked' : ''}>
                            <span>${level}</span>
                        </label>
                    `).join('');
            const markup = `
                <div class="config-option">
                    <span class="config-option-title">Test coverage</span>
                    <label class="single-toggle" data-toggle-name="coverage">
                        <input type="checkbox" name="coverage" value="true" ${settings.testCoverage ? 'checked' : ''} aria-label="Test coverage">
                        <span class="single-toggle-visual" aria-hidden="true">
                            <span class="single-toggle-dot"></span>
                        </span>
                        <span class="single-toggle-text">${settings.testCoverage ? 'On' : 'Off'}</span>
                    </label>
                </div>
                <div class="config-option">
                    <span class="config-option-title">Trace HTTP</span>
                    <label class="single-toggle" data-toggle-name="trace">
                        <input type="checkbox" name="trace" value="true" ${settings.traceHttp ? 'checked' : ''} aria-label="Trace HTTP">
                        <span class="single-toggle-visual" aria-hidden="true">
                            <span class="single-toggle-dot"></span>
                        </span>
                        <span class="single-toggle-text">${settings.traceHttp ? 'On' : 'Off'}</span>
                    </label>
                </div>
                <div class="config-option">
                    <span class="config-option-title">GNS3 server</span>
                    <label class="single-toggle" data-toggle-name="gns3-server">
                        <input type="checkbox" name="gns3-server" value="true" ${settings.gns3Server ? 'checked' : ''} aria-label="GNS3 server">
                        <span class="single-toggle-visual" aria-hidden="true">
                            <span class="single-toggle-dot"></span>
                        </span>
                        <span class="single-toggle-text">${settings.gns3Server ? 'On' : 'Off'}</span>
                    </label>
                </div>
                <div class="config-option">
                    <span class="config-option-title">Verbose level</span>
                    <div class="config-verbose" role="radiogroup" aria-label="Verbose level">
                        ${verboseOptions}
                    </div>
                </div>
                <div class="config-option">
                    <span class="config-option-title">Diff output</span>
                    <label class="single-toggle" data-toggle-name="diff">
                        <input type="checkbox" name="diff" value="true" ${settings.diff ? 'checked' : ''} aria-label="Diff output">
                        <span class="single-toggle-visual" aria-hidden="true">
                            <span class="single-toggle-dot"></span>
                        </span>
                        <span class="single-toggle-text">${settings.diff ? 'On' : 'Off'}</span>
                    </label>
                </div>
                <div class="config-option">
                    <span class="config-option-title">Inventory</span>
                    <select name="inventory" aria-label="Inventory selection"${inventorySelectAttributes}>
                        ${inventoryOptionsMarkup}
                    </select>
                </div>
            `;
            configSettingsContainer.innerHTML = markup;
            syncSingleToggleLabels();
        }

        function updateBulkActionButtons() {
            const hasEntries = configEntries.length > 0;
            if (configClearButton) {
                configClearButton.disabled = !hasEntries;
            }
            if (configSelectAllButton) {
                configSelectAllButton.disabled = !hasEntries;
            }
        }

        function renderConfigOptions() {
            configList.innerHTML = '';
            if (!configEntries.length) {
                const empty = document.createElement('div');
                empty.className = 'config-empty';
                empty.textContent = 'No test files found in tests/integration/harness/components.';
                configList.appendChild(empty);
            } else {
                configEntries.forEach((entry, index) => {
                    const row = document.createElement('div');
                    row.className = 'config-entry';

                    const editButton = document.createElement('button');
                    editButton.type = 'button';
                    editButton.className = 'config-edit-button';
                    editButton.textContent = 'Edit';
                    editButton.addEventListener('click', (event) => {
                        event.preventDefault();
                        event.stopPropagation();
                        void openConfigFile(entry.filename);
                    });

                    const label = document.createElement('label');
                    label.className = 'config-entry-label';

                    const input = document.createElement('input');
                    input.type = 'checkbox';
                    input.value = entry.filename;
                    input.dataset.filename = entry.filename;
                    input.checked = Boolean(entry.selected);
                    const inputId = `config-entry-${index}`;
                    input.id = inputId;

                    const span = document.createElement('span');
                    span.textContent = entry.label;

                    label.appendChild(input);
                    label.appendChild(span);

                    row.appendChild(editButton);
                    row.appendChild(label);
                    configList.appendChild(row);
                });
            }
            renderSettingsOptions();
            updateBulkActionButtons();
        }

        async function fetchConfigOptions() {
            try {
                const response = await fetch('/config', { cache: 'no-store' });
                if (!response.ok) {
                    throw new Error('HTTP ' + response.status);
                }
                const payload = await response.json();
                configEntries = mapEntriesFromPayload(payload.entries);
                configSettings = normalizeSettings(payload.settings);
                inventoryOptions = normalizeInventoryOptions(payload.inventory_options);
                if (Array.isArray(payload.hosts)) {
                    applyHostStatusUpdate(normalizeHostStatuses(payload.hosts));
                }
                configUpdateQueued = false;
                configUpdateInProgress = false;
                if (configUpdateTimer !== null) {
                    window.clearTimeout(configUpdateTimer);
                    configUpdateTimer = null;
                }
                renderConfigOptions();
            } catch (err) {
                console.error('Failed to fetch configuration options', err);
                configEntries = [];
                configSettings = normalizeSettings(null);
                inventoryOptions = [];
                configUpdateQueued = false;
                configUpdateInProgress = false;
                if (configUpdateTimer !== null) {
                    window.clearTimeout(configUpdateTimer);
                    configUpdateTimer = null;
                }
                renderConfigOptions();
                alert('Failed to load configuration options.');
                throw err;
            }
        }

        async function submitConfigOptionsNow() {
            if (!configList) {
                return;
            }
            const selected = Array.from(
                configList.querySelectorAll('input[type="checkbox"]:checked')
            )
                .map((input) => input.dataset.filename)
                .filter((value) => typeof value === 'string');
            const selectionState = collectConfigSelections();
            try {
                const response = await fetch('/config', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        selected,
                        test_coverage: selectionState.testCoverage,
                        trace_http: selectionState.traceHttp,
                        verbose_level: selectionState.verboseLevel,
                        diff: selectionState.diff,
                        gns3_server: selectionState.gns3Server,
                        inventory: selectionState.inventory
                    })
                });
                if (!response.ok) {
                    let detail = '';
                    try {
                        const data = await response.json();
                        detail = data.detail || '';
                    } catch (_) {
                        // ignore
                    }
                    throw new Error(detail || ('HTTP ' + response.status));
                }
                let data = null;
                try {
                    data = await response.json();
                } catch (_) {
                    data = null;
                }
                if (data && Array.isArray(data.entries)) {
                    configEntries = mapEntriesFromPayload(data.entries);
                } else {
                    configEntries = configEntries.map((entry) => ({
                        filename: entry.filename,
                        label: entry.label,
                        selected: selected.includes(entry.filename)
                    }));
                }
                if (data) {
                    inventoryOptions = normalizeInventoryOptions(data.inventory_options);
                    if (Array.isArray(data.hosts)) {
                        applyHostStatusUpdate(normalizeHostStatuses(data.hosts));
                    }
                }
                if (data && data.settings) {
                    configSettings = normalizeSettings(data.settings);
                } else {
                    configSettings = { ...selectionState };
                }
                updateTopologyButtonVisibility(configSettings.gns3Server);
                if (!configUpdateQueued) {
                    renderConfigOptions();
                } else {
                    updateBulkActionButtons();
                }
            } catch (err) {
                const message = err instanceof Error ? err.message : String(err);
                console.error('Failed to update configuration', err);
                alert('Failed to update configuration: ' + message);
            }
        }

        function scheduleConfigUpdate() {
            configUpdateQueued = true;
            if (configUpdateTimer !== null) {
                window.clearTimeout(configUpdateTimer);
            }
            configUpdateTimer = window.setTimeout(() => {
                configUpdateTimer = null;
                void processConfigUpdateQueue();
            }, 150);
        }

        async function processConfigUpdateQueue() {
            if (configUpdateInProgress) {
                configUpdateQueued = true;
                return;
            }
            if (!configUpdateQueued) {
                return;
            }
            configUpdateQueued = false;
            configUpdateInProgress = true;
            try {
                await submitConfigOptionsNow();
            } finally {
                configUpdateInProgress = false;
                if (configUpdateQueued) {
                    void processConfigUpdateQueue();
                }
            }
        }

        function collectConfigSelections() {
            const base = normalizeSettings(configSettings);
            const coverageInput = configPanel.querySelector('input[name="coverage"]');
            const traceInput = configPanel.querySelector('input[name="trace"]');
            const gns3Input = configPanel.querySelector('input[name="gns3-server"]');
            const diffInput = configPanel.querySelector('input[name="diff"]');
            const verboseRadio = configPanel.querySelector('input[name="verbose-level"]:checked');
            const verboseValue = verboseRadio ? Number.parseInt(verboseRadio.value, 10) : base.verboseLevel;
            const inventorySelect = configPanel.querySelector('select[name="inventory"]');
            let inventoryValue = base.inventory;
            if (inventorySelect && !inventorySelect.disabled) {
                const current = inventorySelect.value;
                if (typeof current === 'string') {
                    inventoryValue = current;
                }
            }
            const sanitizedInventory = typeof inventoryValue === 'string' ? inventoryValue.trim() : base.inventory;
            return {
                testCoverage: coverageInput ? coverageInput.checked : base.testCoverage,
                traceHttp: traceInput ? traceInput.checked : base.traceHttp,
                gns3Server: gns3Input ? gns3Input.checked : base.gns3Server,
                diff: diffInput ? diffInput.checked : base.diff,
                verboseLevel: Number.isNaN(verboseValue)
                    ? base.verboseLevel
                    : Math.min(5, Math.max(0, verboseValue)),
                inventory: sanitizedInventory
            };
        }

        function populateConfigFromUI() {
            const inputs = configList.querySelectorAll('input[type="checkbox"]');
            for (const input of inputs) {
                const filename = input.dataset.filename;
                if (!filename) {
                    continue;
                }
                const entry = configEntries.find((item) => item.filename === filename);
                if (entry) {
                    entry.selected = input.checked;
                }
            }
            const selectionState = collectConfigSelections();
            configSettings = { ...selectionState };
            updateTopologyButtonVisibility(selectionState.gns3Server);
        }

        async function openConfigFile(filename) {
            if (!filename) {
                return;
            }
            try {
                const response = await fetch('/config/open', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ filename })
                });
                if (!response.ok) {
                    let detail = '';
                    try {
                        const data = await response.json();
                        detail = data.detail || '';
                    } catch (_) {
                        // ignore
                    }
                    throw new Error(detail || ('HTTP ' + response.status));
                }
            } catch (err) {
                console.error('Failed to open config file', err);
                alert('Failed to open configuration file: ' + err.message);
            }
        }

        function renderDocsEntries(entries) {
            docsList.innerHTML = '';
            if (!Array.isArray(entries) || entries.length === 0) {
                const empty = document.createElement('div');
                empty.className = 'docs-empty';
                empty.textContent = 'No documentation files found.';
                docsList.appendChild(empty);
                return;
            }
            for (const entry of entries) {
                const row = document.createElement('div');
                row.className = 'docs-entry';

                const name = document.createElement('span');
                name.className = 'docs-name';
                name.textContent = entry.label || entry.component;
                row.appendChild(name);

                const buttonGroup = document.createElement('div');
                buttonGroup.className = 'docs-buttons';

                const docButton = document.createElement('button');
                docButton.type = 'button';
                docButton.className = 'docs-button';
                docButton.textContent = 'Document';
                docButton.addEventListener('click', () => {
                    if (entry.html_url) {
                        window.open(entry.html_url, '_blank', 'noopener');
                    }
                });
                buttonGroup.appendChild(docButton);

                const jsonButton = document.createElement('button');
                jsonButton.type = 'button';
                jsonButton.className = 'docs-button';
                jsonButton.textContent = 'JSON';
                if (entry.json_url) {
                    jsonButton.addEventListener('click', () => {
                        window.open(entry.json_url, '_blank', 'noopener');
                    });
                } else {
                    jsonButton.disabled = true;
                    jsonButton.title = 'JSON document not available';
                }
                buttonGroup.appendChild(jsonButton);

                row.appendChild(buttonGroup);
                docsList.appendChild(row);
            }
        }

        async function fetchDocsEntries() {
            const response = await fetch('/documentation/index', { cache: 'no-store' });
            if (!response.ok) {
                throw new Error('HTTP ' + response.status);
            }
            const payload = await response.json();
            if (!payload || !Array.isArray(payload.entries)) {
                return [];
            }
            return payload.entries;
        }

        async function fetchTopologyUrl() {
            const response = await fetch('/topology/url', { cache: 'no-store' });
            if (!response.ok) {
                let detail = '';
                try {
                    const data = await response.json();
                    detail = data.detail || '';
                } catch (_) {
                    // ignore
                }
                throw new Error(detail || ('HTTP ' + response.status));
            }
            const payload = await response.json();
            if (!payload || typeof payload.url !== 'string' || !payload.url.length) {
                throw new Error('Invalid topology URL response');
            }
            try {
                const absolute = new URL(payload.url, window.location.origin);
                return absolute.toString();
            } catch (_) {
                return payload.url;
            }
        }

        async function fetchStatus() {
            try {
                const response = await fetch('/status', { cache: 'no-store' });
                if (!response.ok) {
                    throw new Error('HTTP ' + response.status);
                }
                const payload = await response.json();
                runState.running = Boolean(payload.running);
                if (payload.summary) {
                    runState.summary = payload.summary;
                }
                runState.returncode = Object.prototype.hasOwnProperty.call(payload, 'returncode')
                    ? payload.returncode
                    : null;
                if (Object.prototype.hasOwnProperty.call(payload, 'status')) {
                    runState.status = normalizeRunStatus(payload.status);
                }
                if (Array.isArray(payload.hosts)) {
                    applyHostStatusUpdate(normalizeHostStatuses(payload.hosts));
                }
            } catch (err) {
                console.error('Failed to fetch status', err);
            } finally {
                updateControlUI();
                updateStatusIndicator();
            }
        }

        function updateControlUI() {
            if (runState.running) {
                controlButton.textContent = 'Cancel';
                controlButton.classList.remove('control-start');
                controlButton.classList.add('control-cancel');
                controlButton.disabled = false;
                configButton.disabled = true;
                hideConfigPanel();
            } else {
                controlButton.textContent = 'Start';
                controlButton.classList.add('control-start');
                controlButton.classList.remove('control-cancel');
                controlButton.disabled = false;
                configButton.disabled = false;
            }
        }

        async function sendControl(action, summary) {
            const payload = { action };
            if (summary) {
                payload.summary = summary;
            }
            const response = await fetch('/control', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            if (!response.ok) {
                let detail = '';
                try {
                    const data = await response.json();
                    detail = data.detail || '';
                } catch (_) {
                    // ignore
                }
                throw new Error(detail || ('HTTP ' + response.status));
            }
        }

        async function handleControlClick() {
            if (controlButton.disabled) {
                return;
            }
            if (runState.running) {
                controlButton.disabled = true;
                try {
                    await sendControl('stop');
                } catch (err) {
                    console.error('Failed to stop run', err);
                    alert('Failed to stop run: ' + err.message);
                } finally {
                    await fetchStatus();
                    controlButton.disabled = false;
                }
                return;
            }
            const summary = runState.summary || defaultSummary;
            controlButton.disabled = true;
            runState.running = true;
            runState.returncode = null;
            runState.status = 'run';
            updateControlUI();
            updateStatusIndicator();
            try {
                await sendControl('start', summary);
            } catch (err) {
                console.error('Failed to start run', err);
                alert('Failed to start run: ' + err.message);
            } finally {
                await fetchStatus();
                controlButton.disabled = false;
            }
        }

        function scheduleReconnect() {
            if (reconnectTimer !== null) {
                return;
            }
            setConnectionStatus('Reconnecting…', 'connection-waiting');
            reconnectTimer = window.setTimeout(() => {
                reconnectTimer = null;
                connect();
            }, reconnectDelay);
        }

        function connect() {
            if (socket !== null) {
                socket.close();
                socket = null;
            }
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            setConnectionStatus('Connecting…', 'connection-waiting');
            socket = new WebSocket(protocol + '//' + window.location.host + '/ws');

            socket.addEventListener('open', () => {
                setConnectionStatus('Connected', 'connection-ok');
                void fetchStatus();
            });

            socket.addEventListener('message', (event) => {
                try {
                    const payload = JSON.parse(event.data);
                    if (!payload || typeof payload !== 'object') {
                        return;
                    }
                    if (payload.type === 'dashboard-update') {
                        applyContent(payload.content || '');
                    } else if (payload.type === 'run-state') {
                        runState.running = Boolean(payload.running);
                        if (payload.summary) {
                            runState.summary = payload.summary;
                        }
                        runState.returncode = Object.prototype.hasOwnProperty.call(payload, 'returncode')
                            ? payload.returncode
                            : null;
                        if (Object.prototype.hasOwnProperty.call(payload, 'status')) {
                            runState.status = normalizeRunStatus(payload.status);
                        }
                        updateControlUI();
                        updateStatusIndicator();
                    } else if (payload.type === 'host-status') {
                        applyHostStatusUpdate(normalizeHostStatuses(payload.hosts));
                    } else if (payload.type === 'coverage-link') {
                        updateCoverageButtonState(payload.url ?? null);
                    }
                } catch (err) {
                    console.error('Failed to process message', err);
                }
            });

            socket.addEventListener('close', () => {
                setConnectionStatus('Disconnected', 'connection-error');
                scheduleReconnect();
            });

            socket.addEventListener('error', () => {
                if (socket !== null) {
                    socket.close();
                }
            });
        }

        controlButton.addEventListener('click', () => {
            void handleControlClick();
        });

        if (coverageButton) {
            coverageButton.addEventListener('click', () => {
                if (!coverageUrl) {
                    return;
                }
                const target = resolveCoverageTarget(coverageUrl);
                if (!target) {
                    return;
                }
                const finalTarget = target.startsWith('file://') ? encodeURI(target) : target;
                window.open(finalTarget, '_blank', 'noopener');
            });
        }

        topologyButton.addEventListener('click', () => {
            if (topologyButton.disabled) {
                return;
            }
            topologyButton.disabled = true;
            fetchTopologyUrl()
                .then((url) => {
                    window.open(url, '_blank', 'noopener');
                })
                .catch((err) => {
                    console.error('Failed to open topology view', err);
                    alert('Failed to open topology view: ' + err.message);
                })
                .finally(() => {
                    topologyButton.disabled = false;
                });
        });

        configButton.addEventListener('click', () => {
            if (configButton.disabled) {
                return;
            }
            hideDocsPanel();
            if (isConfigPanelVisible()) {
                hideConfigPanel();
                return;
            }
            configButton.disabled = true;
            fetchConfigOptions()
                .then(() => {
                    configPanel.hidden = false;
                })
                .catch(() => {
                    // handled in fetchConfigOptions
                })
                .finally(() => {
                    configButton.disabled = false;
                });
        });
        function applyBulkSelection(targetState) {
            if (!configList) {
                return;
            }
            let changed = false;
            const inputs = configList.querySelectorAll('input[type="checkbox"]');
            for (const input of inputs) {
                if (input.checked !== targetState) {
                    input.checked = targetState;
                    changed = true;
                }
            }
            if (changed) {
                populateConfigFromUI();
                scheduleConfigUpdate();
            }
        }

        if (configClearButton) {
            configClearButton.addEventListener('click', (event) => {
                event.preventDefault();
                event.stopPropagation();
                applyBulkSelection(false);
            });
        }

        if (configSelectAllButton) {
            configSelectAllButton.addEventListener('click', (event) => {
                event.preventDefault();
                event.stopPropagation();
                applyBulkSelection(true);
            });
        }

        docsButton.addEventListener('click', () => {
            if (docsButton.disabled) {
                return;
            }
            if (isDocsPanelVisible()) {
                hideDocsPanel();
                return;
            }
            docsButton.disabled = true;
            hideConfigPanel();
            fetchDocsEntries()
                .then((entries) => {
                    renderDocsEntries(entries);
                    docsPanel.hidden = false;
                })
                .catch((err) => {
                    console.error('Failed to load documentation entries', err);
                    alert('Failed to load documentation: ' + err.message);
                })
                .finally(() => {
                    docsButton.disabled = false;
                });
        });

        docsBackButton.addEventListener('click', () => {
            hideDocsPanel();
            docsButton.focus();
        });

        configPanel.addEventListener('change', (event) => {
            const target = event.target;
            if (!(target instanceof HTMLInputElement) && !(target instanceof HTMLSelectElement)) {
                return;
            }
            if (target instanceof HTMLInputElement && target.closest('.single-toggle')) {
                updateSingleToggleLabel(target);
            }
            populateConfigFromUI();
            scheduleConfigUpdate();
        });

        async function initialize() {
            updateControlUI();
            updateStatusIndicator();
            updateCoverageButtonState(null);
            await fetchStatus();
            await fetchLatest();
            connect();
        }

        void initialize();
    }());
    </script>
</body>
</html>
"""
def _resolve_ansible_root() -> Path:
    env_path = os.environ.get("ANSIBLE")
    if env_path:
        ansible_root = Path(env_path).expanduser()
        if not ansible_root.is_absolute():
            ansible_root = ansible_root.resolve()
        return ansible_root

    script_path = Path(__file__).resolve()
    for ancestor in script_path.parents:
        candidate = ancestor
        if (candidate / "galaxy.yml").is_file():
            return candidate

    # Fallback to the directory that contains the script if the expected structure is missing.
    return script_path.parent


BASE_DIR = _resolve_ansible_root()
SUMMARY_ROOT = BASE_DIR / "tests" / "integration" / "harness"
SUMMARY_PATTERN = "test*.yml"
DEFAULT_SUMMARY = "test.yml"
CONFIG_ROOT = BASE_DIR / "tests" / "integration" / "harness" / "components"
CONFIG_PATTERN = "test_*.yml"
DEFAULT_SUMMARY_PATH = SUMMARY_ROOT / DEFAULT_SUMMARY
INCLUDE_PREFIX = "- include "
INVENTORY_ROOT = BASE_DIR / "tests" / "integration" / "harness" / "cfg"
SSH_HELPER_SCRIPT = BASE_DIR / "tests" / "integration" / "harness" / "tools" / "ssh_fe_dt.exp"
HOST_SSH_SCRIPT = SSH_HELPER_SCRIPT
STATUS_PATTERN = re.compile(
    r'<div\s+class="summary-status">.*?<span\s+class="status-badge\s+status-(run|pass|fail)"',
    re.IGNORECASE | re.DOTALL,
)

COVERAGE_TEXT_PATTERN = re.compile(
    r"Wrote\s+HTML\s+report\s+to\s+(?P<path>[^\s<]+)",
    re.IGNORECASE,
)
COVERAGE_LINK_PATTERN = re.compile(
    r'href=["\'](?P<path>[^"\'<\s]*(?:coverage|htmlcov)[^"\'<\s]*index\.html[^"\'<\s]*)["\']',
    re.IGNORECASE,
)

DASHBOARD_LOG_PATH = Path("/tmp/dashboard.log")
_LOG_FILE_HANDLE: Optional[object] = None


def _redirect_output_to_log() -> None:
    global _LOG_FILE_HANDLE
    if _LOG_FILE_HANDLE is not None:
        return
    path = DASHBOARD_LOG_PATH
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        log_file = path.open("a", encoding="utf-8", buffering=1)
    except OSError as exc:
        sys.__stderr__.write(f"Failed to open dashboard log {path}: {exc}\n")
        sys.__stderr__.flush()
        return
    timestamp = _dt.datetime.now().isoformat(sep=" ", timespec="seconds")
    header = f"\n[{timestamp}] dashboard_server start (pid {os.getpid()})\n"
    try:
        log_file.write(header)
        log_file.flush()
    except Exception:
        # If writing fails, fall back to original outputs.
        log_file.close()
        sys.__stderr__.write(f"Failed to write to dashboard log {path}\n")
        sys.__stderr__.flush()
        return
    _LOG_FILE_HANDLE = log_file
    sys.stdout = log_file
    sys.stderr = log_file


_redirect_output_to_log()

DOCS_ROOT = BASE_DIR / "docs"
DOC_PREFIX = "extreme_fe_"
TOPOLOGY_CONFIG_PATH = BASE_DIR / "tests" / "integration" / "harness" / "cfg" / "gns3.cfg"
PROJECT_UUID_SCRIPT = BASE_DIR / "tests" / "integration" / "harness" / "tools" / "project_uuid"
HOST_SHELL_SCRIPT = SSH_HELPER_SCRIPT
TERMINAL_CANDIDATES = ("xterm",)


def _resolve_terminal_command() -> str:
    for candidate in TERMINAL_CANDIDATES:
        path = shutil.which(candidate)
        if path:
            return path
    raise FileNotFoundError(
        "No suitable terminal executable found; install xterm or adjust TERMINAL_CANDIDATES"
    )


def _resolve_host_shell_script() -> Path:
    script_path = HOST_SHELL_SCRIPT
    if not script_path.is_file():
        raise FileNotFoundError(f"Host SSH script not found: {script_path}")
    if not os.access(script_path, os.X_OK):
        raise PermissionError(f"Host SSH script is not executable: {script_path}")
    return script_path


def _launch_host_shell(host: str, info: dict[str, Optional[str]]) -> None:
    terminal = _resolve_terminal_command()
    script_path = _resolve_host_shell_script()
    target = str(info.get("target") or host).strip() or host
    user = str(info.get("user")).strip() if info.get("user") else ""
    password = info.get("password") or ""
    env = os.environ.copy()
    env["FE_TARGET_HOST"] = target
    if user:
        env["FE_TARGET_USER"] = user
    if password:
        env["FE_TARGET_PASSWORD"] = password
    command = [
        terminal,
        "-T",
        f"SSH {host}",
        "-e",
        str(script_path),
        target,
    ]
    if user:
        command.append(user)
    if password:
        command.append(password)
    subprocess.Popen(command, env=env, cwd=str(BASE_DIR))


def _format_component_label(component: str) -> str:
    text = component.replace("_", " ").strip()
    if not text:
        return component
    return " ".join(part.capitalize() for part in text.split())


def _discover_documentation_entries() -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    if not DOCS_ROOT.exists():
        return entries
    pattern = f"{DOC_PREFIX}*.html"
    for html_path in sorted(DOCS_ROOT.glob(pattern)):
        component = html_path.stem[len(DOC_PREFIX) :].lower()
        json_path = html_path.with_name(f"{html_path.stem}_doc.json")
        entry = {
            "component": component,
            "label": _format_component_label(component),
            "html_path": html_path,
            "html_filename": html_path.name,
            "json_path": json_path if json_path.exists() else None,
            "json_filename": json_path.name if json_path.exists() else None,
        }
        entries.append(entry)
    return entries


def _locate_documentation_entry(component: str) -> Optional[dict[str, object]]:
    normalized = component.lower()
    for entry in _discover_documentation_entries():
        if entry["component"] == normalized:
            return entry
    return None


def gather_doc_index() -> list[dict[str, Optional[str]]]:
    payload: list[dict[str, Optional[str]]] = []
    for entry in _discover_documentation_entries():
        component = entry["component"]
        payload.append(
            {
                "component": component,
                "label": entry["label"],
                "html_url": f"/documentation/html/{component}",
                "json_url": f"/documentation/json/{component}" if entry["json_path"] is not None else None,
            }
        )
    return payload


def discover_summary_files() -> list[str]:
    if not SUMMARY_ROOT.exists():
        return []
    return sorted(
        path.name
        for path in SUMMARY_ROOT.glob(SUMMARY_PATTERN)
        if path.is_file()
    )


def discover_config_files() -> list[Path]:
    if not CONFIG_ROOT.exists():
        return []
    return sorted(
        path
        for path in CONFIG_ROOT.glob(CONFIG_PATTERN)
        if path.is_file()
    )


def discover_inventory_options() -> list[str]:
    if not INVENTORY_ROOT.exists() or not INVENTORY_ROOT.is_dir():
        return []
    options: list[str] = []
    seen: set[str] = set()
    for path in INVENTORY_ROOT.glob("*.ini"):
        if not path.is_file():
            continue
        name = path.name
        if name not in seen:
            seen.add(name)
            options.append(name)
    return sorted(options, key=str.lower)


def _discover_inventory_hosts(inventory_path: Path) -> list[dict[str, Optional[str]]]:
    if not inventory_path.is_file():
        return []
    command = ["ansible-inventory", "-i", str(inventory_path), "--list"]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return []
    if result.returncode != 0:
        return []
    payload_text = result.stdout or ""
    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError:
        return []
    hosts: set[str] = set()
    hostvars: dict[str, dict[str, object]] = {}
    if isinstance(payload, dict):
        meta = payload.get("_meta")
        if isinstance(meta, dict):
            raw_hostvars = meta.get("hostvars")
            if isinstance(raw_hostvars, dict):
                hostvars = {
                    str(name): value
                    for name, value in raw_hostvars.items()
                    if isinstance(name, str) and isinstance(value, dict)
                }
                hosts.update(hostvars.keys())
        for value in payload.values():
            if not isinstance(value, dict):
                continue
            group_hosts = value.get("hosts")
            if isinstance(group_hosts, list):
                for host in group_hosts:
                    if isinstance(host, str):
                        hosts.add(host)

    def _resolve_target(hostname: str) -> str:
        info = hostvars.get(hostname, {})
        if isinstance(info, dict):
            for key in (
                "ansible_host",
                "ansible_host_ipv4",
                "ansible_ssh_host",
                "ipv4_address",
                "ip",
            ):
                value = info.get(key)
                if value:
                    return str(value).strip() or hostname
        return hostname

    def _resolve_user(hostname: str) -> Optional[str]:
        info = hostvars.get(hostname, {})
        if isinstance(info, dict):
            for key in (
                "ansible_user",
                "ansible_ssh_user",
                "user",
                "username",
            ):
                value = info.get(key)
                if value:
                    return str(value).strip() or None
        return None

    def _resolve_password(hostname: str) -> Optional[str]:
        info = hostvars.get(hostname, {})
        if isinstance(info, dict):
            for key in (
                "ansible_password",
                "ansible_ssh_pass",
                "password",
                "ansible_pass",
            ):
                value = info.get(key)
                if value:
                    text = str(value)
                    return text if text else None
        return None

    entries: list[dict[str, Optional[str]]] = []
    for host in sorted({host.strip() for host in hosts if host and host.strip()}):
        entry: dict[str, Optional[str]] = {
            "host": host,
            "target": _resolve_target(host),
        }
        user_value = _resolve_user(host)
        password_value = _resolve_password(host)
        if user_value:
            entry["user"] = user_value
        if password_value:
            entry["password"] = password_value
        entries.append(entry)
    return entries


def _build_terminal_command(title: str, script_path: Path, target: str, user: str, password: str) -> list[str]:
    terminal_path = shutil.which("xterm")
    if not terminal_path:
        raise FileNotFoundError("xterm executable not found in PATH; install xterm or update configuration")
    window_title = title.strip() or target
    return [
        terminal_path,
        "-geometry",
        "120x60",
        "-fg",
        "white",
        "-bg",
        "blue",
        "-title",
        window_title,
        "-e",
        str(script_path),
        target,
        user,
        password,
    ]


def _read_gns_server_settings() -> tuple[str, str]:
    if not TOPOLOGY_CONFIG_PATH.is_file():
        raise FileNotFoundError(f"Topology config file not found: {TOPOLOGY_CONFIG_PATH}")
    host: Optional[str] = None
    port: Optional[str] = None
    for raw_line in TOPOLOGY_CONFIG_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"\'')
        if key == "GNS3_SERVER_HOST" and value:
            host = value
        elif key == "GNS3_SERVER_PORT" and value:
            port = value
    if not host:
        raise ValueError("GNS3_SERVER_HOST is missing in topology config")
    if not port:
        raise ValueError("GNS3_SERVER_PORT is missing in topology config")
    return host, port


def _fetch_project_uuid() -> str:
    if not PROJECT_UUID_SCRIPT.is_file():
        raise FileNotFoundError(f"Project UUID script not found: {PROJECT_UUID_SCRIPT}")
    command = [str(PROJECT_UUID_SCRIPT)]
    result = subprocess.run(
        command,
        cwd=str(PROJECT_UUID_SCRIPT.parent),
        capture_output=True,
        text=True,
        check=False,
    )
    output = (result.stdout or "").strip()
    if result.returncode != 0:
        error_output = (result.stderr or "").strip()
        detail = error_output or output or f"project_uuid exited with status {result.returncode}"
        raise RuntimeError(detail)
    if not output:
        raise ValueError("project_uuid returned empty result")
    return output


def build_topology_url() -> str:
    host, port = _read_gns_server_settings()
    project_id = _fetch_project_uuid()
    normalized_host = host.strip()
    normalized_port = port.strip()
    if normalized_port and not normalized_port.isdigit():
        raise ValueError(f"Invalid GNS3_SERVER_PORT: {normalized_port}")
    scheme = "http"
    base = f"{scheme}://{normalized_host}:{normalized_port}"
    return f"{base}/static/web-ui/server/1/project/{project_id}"


def _resolve_editor_command() -> list[str]:
    override = os.environ.get("VSCODE_CLI") or os.environ.get("CODE_CMD")
    if override:
        parts = shlex.split(override)
    else:
        code_cli = shutil.which("code")
        if not code_cli:
            raise FileNotFoundError("VS Code command line 'code' not found. Set VSCODE_CLI to override.")
        parts = [code_cli]
    if not parts:
        raise FileNotFoundError("VS Code command is empty.")
    command_path = Path(parts[0])
    if not command_path.is_absolute():
        resolved = shutil.which(parts[0])
        if resolved is None:
            raise FileNotFoundError(f"VS Code command '{parts[0]}' not found in PATH.")
        parts[0] = resolved
    elif not command_path.exists():
        raise FileNotFoundError(f"VS Code command '{command_path}' does not exist.")
    return parts


def _open_path_in_editor(path: Path) -> None:
    command = _resolve_editor_command()
    target = f"{path}:1"
    subprocess.Popen(command + ["--goto", target], cwd=str(BASE_DIR))


def _format_config_label(filename: str) -> str:
    label = filename
    if label.startswith("test_"):
        label = label[len("test_"):]
    if label.endswith(".yml"):
        label = label[:-4]
    return label


def read_current_includes() -> set[str]:
    if not DEFAULT_SUMMARY_PATH.exists():
        return set()
    includes: set[str] = set()
    for raw_line in DEFAULT_SUMMARY_PATH.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if stripped.startswith(INCLUDE_PREFIX):
            includes.add(stripped[len(INCLUDE_PREFIX):].strip())
    return includes


def gather_config_entries() -> list[dict[str, object]]:
    files = discover_config_files()
    selected = read_current_includes()
    return [
        {
            "filename": path.name,
            "label": _format_config_label(path.name),
            "selected": path.name in selected,
        }
        for path in files
    ]


def parse_playbook_args(arg_string: str) -> tuple[int, bool]:
    verbose_level = 0
    diff_enabled = False
    for token in arg_string.split():
        if token.startswith("-") and token.count("v") == len(token) - 1:
            verbose_level = min(5, max(verbose_level, len(token) - 1))
        elif token == "--diff":
            diff_enabled = True
    return verbose_level, diff_enabled


def format_playbook_args(verbose_level: int, diff_enabled: bool) -> str:
    parts: list[str] = []
    level = max(0, min(5, int(verbose_level)))
    if level > 0:
        parts.append("-" + "v" * level)
    if diff_enabled:
        parts.append("--diff")
    return " ".join(parts)


def _normalize_inventory_setting_for_ui(raw: str) -> str:
    text = raw.strip()
    if not text:
        return ""
    try:
        candidate = Path(text)
    except TypeError:
        return ""
    options = discover_inventory_options()
    if candidate.name in options:
        return candidate.name
    try:
        resolved = candidate if candidate.is_absolute() else (BASE_DIR / candidate).resolve()
    except (OSError, RuntimeError):
        resolved = (BASE_DIR / candidate).resolve()
    try:
        relative = resolved.relative_to(INVENTORY_ROOT)
    except ValueError:
        relative = None
    else:
        if len(relative.parts) == 1:
            return relative.name
    for name in options:
        if text.endswith(f"/{name}") or text == name:
            return name
    return text


def resolve_inventory_selection(selection: str) -> Optional[Path]:
    text = (selection or "").strip()
    if not text:
        return None
    candidates: list[Path] = []
    raw_path = Path(text)
    if raw_path.is_absolute():
        candidates.append(raw_path)
    else:
        candidates.append((BASE_DIR / raw_path))
    candidates.append(INVENTORY_ROOT / text)
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        try:
            resolved = candidate.resolve(strict=True)
        except (FileNotFoundError, OSError, RuntimeError):
            continue
        if resolved.is_file():
            return resolved
    return None


def read_run_options() -> dict[str, object]:
    defaults = {
        "test_coverage": False,
        "trace_http": False,
        "verbose_level": 0,
        "diff": False,
        "inventory": "",
        "gns3_server": True,
    }
    if not DEFAULT_SUMMARY_PATH.exists():
        return dict(defaults)
    test_coverage = defaults["test_coverage"]
    trace_http = defaults["trace_http"]
    verbose_level = defaults["verbose_level"]
    diff_enabled = defaults["diff"]
    inventory_value = defaults["inventory"]
    gns3_enabled = defaults["gns3_server"]
    for raw_line in DEFAULT_SUMMARY_PATH.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        bare = stripped
        lowered = bare.lower()
        if lowered.startswith("test_coverage:"):
            value = bare.split(":", 1)[1].strip().lower()
            test_coverage = value in {"true", "1", "yes", "on"}
        elif lowered.startswith("trace_http:"):
            value = bare.split(":", 1)[1].strip().lower()
            trace_http = value in {"true", "1", "yes", "on"}
        elif lowered.startswith("playbook_args:"):
            arg_string = bare.split(":", 1)[1].strip()
            verbose_level, diff_enabled = parse_playbook_args(arg_string)
        elif lowered.startswith("inventory:"):
            value = bare.split(":", 1)[1].strip()
            if value:
                inventory_value = _normalize_inventory_setting_for_ui(value)
        elif lowered.startswith("gns3_server:"):
            value = bare.split(":", 1)[1].strip().lower()
            gns3_enabled = value not in {"false", "0", "no", "off"}
    return {
        "test_coverage": test_coverage,
        "trace_http": trace_http,
        "verbose_level": verbose_level,
        "diff": diff_enabled,
        "inventory": inventory_value,
        "gns3_server": gns3_enabled,
    }


def gather_config_state() -> dict[str, object]:
    return {
        "entries": gather_config_entries(),
        "settings": read_run_options(),
        "inventory_options": discover_inventory_options(),
    }


def extract_dashboard_status(content: str) -> Optional[str]:
    if not content:
        return None
    match = STATUS_PATTERN.search(content)
    if not match:
        return None
    status = match.group(1).lower()
    if status in {"run", "pass", "fail"}:
        return status
    return None


def extract_coverage_report_path(content: str) -> Optional[str]:
    if not content:
        return None
    for pattern in (COVERAGE_TEXT_PATTERN, COVERAGE_LINK_PATTERN):
        match = pattern.search(content)
        if not match:
            continue
        raw_path = match.group("path")
        if not raw_path:
            continue
        path = html.unescape(raw_path).strip()
        if path:
            return path
    return None


def resolve_coverage_filesystem_path(raw: Optional[str]) -> Optional[Path]:
    text = (raw or "").strip()
    if not text:
        return None
    candidates: list[Path] = []
    lowered = text.lower()
    if lowered.startswith("file://"):
        parsed = urlparse(text)
        path_part = unquote(parsed.path or "")
        if path_part:
            candidates.append(Path(path_part))
            distro = os.environ.get("WSL_DISTRO_NAME")
            if distro:
                stripped = path_part.lstrip("/")
                prefix = f"{distro}/"
                if stripped.startswith(prefix):
                    trimmed = "/" + stripped[len(prefix):]
                    candidates.append(Path(trimmed))
            stripped = path_part.lstrip("/")
            if "/" in stripped:
                without_prefix = stripped.split("/", 1)[1]
                if without_prefix:
                    candidates.append(Path("/" + without_prefix))
        if parsed.netloc:
            combined = f"/{parsed.netloc}{path_part}"
            candidates.append(Path(combined))
    else:
        candidates.append(Path(text))
        if not os.path.isabs(text):
            candidates.append(BASE_DIR / text)
    seen: set[str] = set()
    ordered: list[Path] = []
    for candidate in candidates:
        key = str(candidate)
        if key not in seen:
            seen.add(key)
            ordered.append(candidate)
    for candidate in ordered:
        try:
            resolved = candidate.resolve(strict=False)
        except (OSError, RuntimeError):
            continue
        if resolved.exists():
            return resolved
    for candidate in ordered:
        try:
            return candidate.resolve(strict=False)
        except (OSError, RuntimeError):
            continue
    return None


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def update_test_configuration(
    selected_files: list[str],
    *,
    test_coverage: bool,
    trace_http: bool,
    verbose_level: int,
    diff: bool,
    gns3_server: bool,
    inventory: Optional[str],
) -> None:
    summary_path = DEFAULT_SUMMARY_PATH
    if not summary_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {summary_path}")
    available = {path.name for path in discover_config_files()}
    available_inventory = set(discover_inventory_options())
    unique_selected: list[str] = []
    seen: set[str] = set()
    for name in selected_files:
        if name in available and name not in seen:
            unique_selected.append(name)
            seen.add(name)
    original_lines = summary_path.read_text(encoding="utf-8").splitlines()
    new_include_lines = [f"{INCLUDE_PREFIX}{name}" for name in unique_selected]
    new_args_value = format_playbook_args(verbose_level, diff)
    inventory_action: Optional[str] = None
    inventory_entry_value: Optional[str] = None
    if inventory is not None:
        trimmed = inventory.strip()
        if trimmed:
            inventory_action = "set"
            if trimmed in available_inventory:
                inventory_entry_value = f"tests/integration/harness/cfg/{trimmed}"
            else:
                inventory_entry_value = trimmed
        else:
            inventory_action = "clear"
    updated_lines: list[str] = []
    includes_written = False
    coverage_written = False
    trace_written = False
    args_written = False
    inventory_written = False
    gns3_written = False
    for line in original_lines:
        stripped = line.strip()
        bare = stripped.lstrip("#").strip() if stripped.startswith("#") else stripped
        lowered = bare.lower()
        indent = line[: len(line) - len(line.lstrip())]
        if lowered.startswith("inventory:"):
            inventory_written = True
            if inventory_action == "set" and inventory_entry_value is not None:
                updated_lines.append(f"{indent}inventory: {inventory_entry_value}")
            elif inventory_action == "clear":
                continue
            else:
                updated_lines.append(line)
            continue
        if lowered.startswith("test_coverage:"):
            updated_lines.append(f"{indent}test_coverage: {'true' if test_coverage else 'false'}")
            coverage_written = True
            continue
        if lowered.startswith("trace_http:"):
            updated_lines.append(f"{indent}trace_http: {'true' if trace_http else 'false'}")
            trace_written = True
            continue
        if lowered.startswith("playbook_args:"):
            suffix = f" {new_args_value}" if new_args_value else ""
            updated_lines.append(f"{indent}playbook_args:{suffix}")
            args_written = True
            continue
        if stripped.startswith(INCLUDE_PREFIX):
            if not includes_written:
                updated_lines.extend(new_include_lines)
                includes_written = True
            continue
        if lowered.startswith("gns3_server:"):
            updated_lines.append(f"{indent}gns3_server: {'true' if gns3_server else 'false'}")
            gns3_written = True
            continue
        updated_lines.append(line)
    pending_lines: list[str] = []
    if inventory_action == "set" and not inventory_written and inventory_entry_value is not None:
        pending_lines.append(f"inventory: {inventory_entry_value}")
    if not coverage_written:
        pending_lines.append(f"test_coverage: {'true' if test_coverage else 'false'}")
    if not trace_written:
        pending_lines.append(f"trace_http: {'true' if trace_http else 'false'}")
    if not gns3_written:
        pending_lines.append(f"gns3_server: {'true' if gns3_server else 'false'}")
    if not args_written:
        suffix = f" {new_args_value}" if new_args_value else ""
        pending_lines.append(f"playbook_args:{suffix}")
    if pending_lines:
        insert_index = next(
            (idx for idx, current in enumerate(updated_lines) if current.strip().startswith("Tests:")),
            len(updated_lines),
        )
        updated_lines[insert_index:insert_index] = pending_lines
    if not includes_written and new_include_lines:
        if updated_lines and updated_lines[-1].strip():
            updated_lines.append("")
        updated_lines.extend(new_include_lines)
    summary_path.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")


class DashboardUpdate(BaseModel):
    content: str


class ControlRequest(BaseModel):
    action: Literal["start", "stop"]
    summary: Optional[str] = None


class ConfigUpdateRequest(BaseModel):
    selected: list[str] = Field(default_factory=list)
    test_coverage: bool = False
    trace_http: bool = False
    verbose_level: int = Field(default=0, ge=0, le=5)
    diff: bool = False
    gns3_server: bool = True
    inventory: Optional[str] = None


class ConfigOpenRequest(BaseModel):
    filename: str


class HostShellRequest(BaseModel):
    host: str


class ConnectionManager:
    """Track connected WebSocket clients and broadcast dashboard and run updates."""

    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()
        self._latest_dashboard: str = ""
        self._latest_status: str = "na"
        self._latest_run_state: dict[str, Optional[object]] = {
            "running": False,
            "summary": DEFAULT_SUMMARY,
            "returncode": None,
            "status": "na",
        }
        self._coverage_url: Optional[str] = None
        self._coverage_fs_root: Optional[Path] = None
        self._coverage_entry: Optional[str] = None
        self._host_status: dict[str, bool] = {}
        self._host_targets: dict[str, str] = {}
        self._host_connection_info: dict[str, dict[str, Optional[str]]] = {}

    @property
    def latest(self) -> str:
        return self._latest_dashboard

    def set_latest_dashboard(self, content: str) -> Optional[str]:
        self._latest_dashboard = content
        status = extract_dashboard_status(content)
        if status is not None and status != self._latest_status:
            self._latest_status = status
            self._latest_run_state["status"] = status
            return status
        return None

    def set_latest_run_state(
        self,
        *,
        running: bool,
        summary: Optional[str],
        returncode: Optional[int],
        status: Optional[str] = None,
    ) -> None:
        if status is not None:
            normalized = str(status).lower()
            if normalized not in {"na", "run", "pass", "fail"}:
                normalized = "na"
            self._latest_status = normalized
        self._latest_run_state = {
            "running": running,
            "summary": summary,
            "returncode": returncode,
            "status": self._latest_status,
        }

    def current_run_state(self) -> dict[str, Optional[object]]:
        return dict(self._latest_run_state)

    def set_coverage_url(self, url: Optional[str]) -> bool:
        normalized: Optional[str] = None
        fs_root: Optional[Path] = None
        entry: Optional[str] = None
        if url:
            resolved_path = resolve_coverage_filesystem_path(url)
            if resolved_path is not None:
                try:
                    resolved_path = resolved_path.resolve(strict=False)
                except (OSError, RuntimeError):
                    pass
                if resolved_path.is_dir():
                    fs_root = resolved_path
                    entry = "index.html"
                else:
                    fs_root = resolved_path.parent
                    entry = resolved_path.name
                if fs_root is not None and entry:
                    try:
                        fs_root = fs_root.resolve(strict=False)
                    except (OSError, RuntimeError):
                        pass
                    normalized = f"/coverage/latest/{entry}"
            if normalized is None:
                candidate = url.strip()
                normalized = candidate if candidate else None
        changed = (
            normalized != self._coverage_url
            or fs_root != self._coverage_fs_root
            or entry != self._coverage_entry
        )
        if not changed:
            return False
        self._coverage_url = normalized
        self._coverage_fs_root = fs_root
        self._coverage_entry = entry
        return True

    def get_coverage_url(self) -> Optional[str]:
        return self._coverage_url

    def get_coverage_filesystem_root(self) -> Optional[Path]:
        return self._coverage_fs_root

    def get_coverage_entry(self) -> Optional[str]:
        return self._coverage_entry

    def _host_status_payload(self) -> list[dict[str, object]]:
        return [
            {
                "host": host,
                "reachable": bool(status),
                "target": self._host_targets.get(host),
            }
            for host, status in sorted(self._host_status.items(), key=lambda item: item[0].lower())
        ]

    def get_host_status_snapshot(self) -> list[dict[str, object]]:
        return self._host_status_payload()

    async def broadcast_host_statuses(self) -> None:
        await self._broadcast_message({"type": "host-status", "hosts": self._host_status_payload()})

    async def set_host_inventory(
        self,
        hosts: Sequence[object],
        *,
        reset: bool = False,
    ) -> None:
        previous_hosts = list(self._host_status.keys())
        previous_targets = dict(self._host_targets)
        cleaned: list[tuple[str, str]] = []
        seen: set[str] = set()
        connection_info: dict[str, dict[str, Optional[str]]] = {}

        for entry in hosts:
            host_name: Optional[str]
            target_value: Optional[str]
            user_value: Optional[str] = None
            password_value: Optional[str] = None
            if isinstance(entry, tuple) and len(entry) >= 2:
                host_name = str(entry[0]) if entry[0] is not None else None
                target_value = str(entry[1]) if entry[1] is not None else None
            elif isinstance(entry, dict):
                raw_host = entry.get("host") or entry.get("name")
                raw_target = (
                    entry.get("target")
                    or entry.get("address")
                    or entry.get("ip")
                    or entry.get("ansible_host")
                )
                raw_user = (
                    entry.get("user")
                    or entry.get("username")
                    or entry.get("ansible_user")
                    or entry.get("ansible_ssh_user")
                )
                raw_password = (
                    entry.get("password")
                    or entry.get("ansible_password")
                    or entry.get("ansible_ssh_pass")
                    or entry.get("ansible_pass")
                )
                host_name = str(raw_host) if raw_host is not None else None
                if raw_target is None:
                    raw_target = raw_host
                target_value = str(raw_target) if raw_target is not None else None
                if raw_user is not None:
                    user_value = str(raw_user)
                if raw_password is not None:
                    password_value = str(raw_password)
            elif isinstance(entry, str):
                host_name = entry
                target_value = entry
            else:
                host_name = str(entry) if entry is not None else None
                target_value = host_name

            if not host_name:
                continue
            normalized_host = host_name.strip()
            if not normalized_host or normalized_host in seen:
                continue
            seen.add(normalized_host)
            normalized_target = (target_value or normalized_host).strip() or normalized_host
            cleaned.append((normalized_host, normalized_target))
            connection_info[normalized_host] = {
                "target": normalized_target,
                "user": user_value.strip() if isinstance(user_value, str) else None,
                "password": password_value if isinstance(password_value, str) else None,
            }

        cleaned_names = [host for host, _ in cleaned]
        if reset:
            new_status: dict[str, bool] = {host: False for host in cleaned_names}
        else:
            new_status = {host: self._host_status.get(host, False) for host in cleaned_names}

        targets_changed = (
            len(previous_targets) != len(cleaned)
            or any(previous_targets.get(host) != target for host, target in cleaned)
        )

        changed = reset or previous_hosts != cleaned_names or targets_changed
        self._host_status = new_status
        self._host_targets = {host: target for host, target in cleaned}
        self._host_connection_info = connection_info
        if changed:
            await self.broadcast_host_statuses()

    async def update_host_status(self, host: str, reachable: bool) -> None:
        normalized = host.strip()
        if not normalized or normalized not in self._host_status:
            return
        reachable_flag = bool(reachable)
        if self._host_status.get(normalized) == reachable_flag:
            return
        self._host_status[normalized] = reachable_flag
        await self.broadcast_host_statuses()

    def get_host_connection_info(self, host: str) -> Optional[dict[str, Optional[str]]]:
        normalized = host.strip() if isinstance(host, str) else ""
        if not normalized:
            return None
        info = self._host_connection_info.get(normalized)
        if info is None:
            return None
        target = info.get("target") or self._host_targets.get(normalized) or normalized
        return {
            "target": target,
            "user": info.get("user"),
            "password": info.get("password"),
        }

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)
            latest_dashboard = self._latest_dashboard
            latest_run_state = dict(self._latest_run_state)
            latest_coverage = self._coverage_url
        try:
            if latest_dashboard:
                await websocket.send_json({"type": "dashboard-update", "content": latest_dashboard})
            await websocket.send_json(
                {
                    "type": "run-state",
                    "running": latest_run_state.get("running", False),
                    "summary": latest_run_state.get("summary"),
                    "returncode": latest_run_state.get("returncode"),
                    "status": latest_run_state.get("status", "na"),
                }
            )
            if latest_coverage:
                await websocket.send_json({"type": "coverage-link", "url": latest_coverage})
            await websocket.send_json({"type": "host-status", "hosts": self._host_status_payload()})
        except Exception:
            await self.disconnect(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(websocket)

    async def _broadcast_message(self, message: dict[str, object]) -> None:
        async with self._lock:
            recipients = list(self._connections)
        stale: list[WebSocket] = []
        for ws in recipients:
            try:
                await ws.send_json(message)
            except Exception:
                stale.append(ws)
        if stale:
            async with self._lock:
                for ws in stale:
                    self._connections.discard(ws)

    async def broadcast_dashboard(self, content: str) -> None:
        self.set_latest_dashboard(content)
        await self._broadcast_message({"type": "dashboard-update", "content": content})

    async def broadcast_coverage_url(self, url: Optional[str]) -> None:
        await self._broadcast_message({"type": "coverage-link", "url": url})

    async def broadcast_run_state(
        self,
        *,
        running: bool,
        summary: Optional[str],
        returncode: Optional[int],
        status: Optional[str] = None,
    ) -> None:
        self.set_latest_run_state(
            running=running,
            summary=summary,
            returncode=returncode,
            status=status,
        )
        await self._broadcast_message(
            {
                "type": "run-state",
                "running": running,
                "summary": summary,
                "returncode": returncode,
                "status": self._latest_status,
            }
        )


def _read_env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    if parsed <= 0:
        return default
    return parsed


def _determine_ping_timeouts() -> list[int]:
    primary = _read_env_int("DASHBOARD_PING_TIMEOUT", 0)
    if primary <= 0:
        primary = _read_env_int("RUN_TEST_PING_TIMEOUT", 1)
    primary = max(1, primary)
    fallback = _read_env_int("DASHBOARD_PING_FALLBACK_TIMEOUT", 0)
    if fallback <= 0:
        fallback = _read_env_int("RUN_TEST_PING_FALLBACK_TIMEOUT", 3)
    fallback = max(primary, fallback)
    timeouts: list[int] = []
    for value in (primary, fallback):
        if value not in timeouts:
            timeouts.append(value)
    return timeouts


class HostReachabilityMonitor:
    """Continuously monitor reachability of inventory hosts via ping."""

    def __init__(self, manager: ConnectionManager, interval: float = 1.0) -> None:
        self._manager = manager
        self._interval = max(0.5, float(interval))
        self._lock = asyncio.Lock()
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._inventory: Optional[Path] = None
        self._ping_path: Optional[str] = shutil.which("ping")
        self._stopped = False
        self._host_targets: dict[str, str] = {}
        self._ping_timeouts = _determine_ping_timeouts()

    async def set_inventory(self, inventory_path: Optional[Path]) -> None:
        if self._stopped:
            return
        resolved: Optional[Path] = None
        hosts: list[dict[str, Optional[str]]] = []
        if inventory_path is not None:
            try:
                resolved_candidate = inventory_path.resolve(strict=True)
            except (FileNotFoundError, OSError, RuntimeError):
                resolved_candidate = None
            if resolved_candidate is not None and resolved_candidate.is_file():
                hosts = await asyncio.to_thread(_discover_inventory_hosts, resolved_candidate)
                resolved = resolved_candidate
        normalized_hosts: list[dict[str, Optional[str]]] = []
        seen: set[str] = set()
        for entry in hosts:
            if not isinstance(entry, dict):
                continue
            host_name = str(entry.get("host") or "").strip()
            if not host_name or host_name in seen:
                continue
            seen.add(host_name)
            target_value = str(entry.get("target") or "").strip() or host_name
            user_value = str(entry.get("user") or "").strip()
            password_value = entry.get("password")
            host_entry: dict[str, Optional[str]] = {
                "host": host_name,
                "target": target_value,
            }
            if user_value:
                host_entry["user"] = user_value
            if isinstance(password_value, str) and password_value:
                host_entry["password"] = password_value
            normalized_hosts.append(host_entry)
        async with self._lock:
            if self._stopped:
                return
            current_hosts = set(self._tasks.keys())
            desired_hosts = {item["host"] for item in normalized_hosts}
            same_targets = all(
                self._host_targets.get(item["host"]) == item["target"]
                for item in normalized_hosts
            )
            if resolved == self._inventory and current_hosts == desired_hosts and same_targets:
                return
            await self._replace_hosts(normalized_hosts, resolved)

    async def close(self) -> None:
        async with self._lock:
            self._stopped = True
            await self._stop_locked()
            self._inventory = None
        await self._manager.set_host_inventory([], reset=True)

    async def _replace_hosts(
        self,
        hosts: list[dict[str, Optional[str]]],
        inventory: Optional[Path],
    ) -> None:
        previous_inventory = self._inventory
        await self._stop_locked()
        inventory_changed = previous_inventory != inventory
        self._inventory = inventory
        await self._manager.set_host_inventory(hosts, reset=inventory_changed)
        if not hosts:
            return
        self._host_targets = {entry["host"]: entry["target"] for entry in hosts}
        for entry in hosts:
            host = entry["host"]
            target = entry["target"]
            task = asyncio.create_task(self._monitor_host(host, target))
            self._tasks[host] = task

    async def _stop_locked(self) -> None:
        tasks = list(self._tasks.values())
        self._tasks.clear()
        self._host_targets.clear()
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _monitor_host(self, host: str, target: str) -> None:
        try:
            while True:
                try:
                    reachable = await self._ping_host(target)
                    await self._manager.update_host_status(host, reachable)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    # Suppress transient errors while continuing monitoring.
                    pass
                try:
                    await asyncio.sleep(self._interval)
                except asyncio.CancelledError:
                    raise
        except asyncio.CancelledError:
            return

    async def _ping_host(self, target: str) -> bool:
        ping_cmd = self._ping_path or shutil.which("ping")
        if not ping_cmd:
            self._ping_path = None
            return False
        self._ping_path = ping_cmd
        for timeout in self._ping_timeouts:
            try:
                process = await asyncio.create_subprocess_exec(
                    ping_cmd,
                    "-c",
                    "1",
                    "-W",
                    str(timeout),
                    target,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
            except (FileNotFoundError, OSError):
                self._ping_path = None
                return False
            except Exception:
                return False
            try:
                returncode = await process.wait()
            except Exception:
                return False
            if returncode == 0:
                return True
        return False


manager = ConnectionManager()
app = FastAPI(title="Extreme FE Dashboard", version="1.0.0")
host_monitor = HostReachabilityMonitor(manager)


async def _launch_host_shell(host: str) -> None:
    normalized = host.strip() if isinstance(host, str) else ""
    if not normalized:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Host name is required")
    info = manager.get_host_connection_info(normalized)
    if info is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown host '{normalized}'")
    target = (info.get("target") or normalized).strip() or normalized
    user = (info.get("user") or "").strip()
    password = info.get("password")
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Inventory for host '{normalized}' is missing ansible_user",
        )
    if not password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Inventory for host '{normalized}' is missing ansible_password",
        )
    script_path = HOST_SSH_SCRIPT
    if not script_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"SSH helper script not found at {script_path}",
        )
    try:
        command = _build_terminal_command(normalized, script_path, target, user, str(password))
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
    loop = asyncio.get_running_loop()

    def _spawn() -> None:
        env = os.environ.copy()
        subprocess.Popen(command, env=env)

    try:
        await loop.run_in_executor(None, _spawn)
    except Exception as exc:  # pragma: no cover - defensive logging path
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to launch terminal for host '{normalized}': {exc}",
        ) from exc


async def _refresh_host_monitor_from_settings(settings: Optional[dict[str, object]]) -> None:
    selection: str = ""
    if isinstance(settings, dict):
        value = settings.get("inventory")
        if isinstance(value, str):
            selection = value
        elif value is not None:
            selection = str(value)
    inventory_path = resolve_inventory_selection(selection) if selection else None
    await host_monitor.set_inventory(inventory_path)


@app.on_event("startup")
async def _dashboard_startup() -> None:
    settings = await asyncio.to_thread(read_run_options)
    await _refresh_host_monitor_from_settings(settings)


@app.on_event("shutdown")
async def _dashboard_shutdown() -> None:
    await host_monitor.close()


def _coverage_response(resource: Optional[str]) -> FileResponse:
    root = manager.get_coverage_filesystem_root()
    entry = manager.get_coverage_entry()
    if root is None or entry is None:
        raise HTTPException(status_code=404, detail="Coverage report not available")
    try:
        root_resolved = root.resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise HTTPException(status_code=500, detail=f"Coverage directory unavailable: {exc}") from exc
    relative = (resource or "").strip()
    if not relative:
        relative = entry
    cleaned = relative.lstrip("/")
    if not cleaned:
        cleaned = entry
    target = (root_resolved / cleaned).resolve(strict=False)
    if not _is_relative_to(target, root_resolved):
        raise HTTPException(status_code=404, detail="Coverage resource not found")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Coverage resource not found")
    return FileResponse(str(target))


class RunManager:
    """Manage the lifecycle of run_test.py processes."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._process: Optional[subprocess.Popen[str]] = None
        self._summary: Optional[Path] = None
        self._returncode: Optional[int] = None

    async def start(self, summary_name: str) -> Path:
        summary_path = self._resolve_summary(summary_name)
        async with self._lock:
            if self._process is not None and self._process.poll() is None:
                raise RuntimeError("run_test.py is already running")
            env = os.environ.copy()
            env.setdefault("RUN_TEST_DASHBOARD_PUSH_URL", "http://127.0.0.1:4000/update")
            cmd = [
                sys.executable,
                str((BASE_DIR / "tests" / "integration" / "harness" / "run_test.py").resolve()),
                str(summary_path),
            ]
            process = subprocess.Popen(cmd, cwd=str(BASE_DIR), env=env)
            self._process = process
            self._summary = summary_path
            self._returncode = None
        if manager.set_coverage_url(None):
            await manager.broadcast_coverage_url(None)
        await manager.broadcast_run_state(
            running=True,
            summary=summary_path.name,
            returncode=None,
            status="run",
        )
        asyncio.create_task(self._watch_process(process, summary_path))
        return summary_path

    async def stop(self) -> bool:
        async with self._lock:
            if self._process is None or self._process.poll() is not None:
                return False
            process = self._process
            summary = self._summary
        if process is None:
            return False
        returncode = await asyncio.to_thread(self._terminate_process, process)
        async with self._lock:
            if self._process is process:
                self._process = None
                self._returncode = returncode
        status_value: Optional[str]
        if returncode is None:
            status_value = None
        else:
            status_value = "pass" if returncode == 0 else "fail"
        await manager.broadcast_run_state(
            running=False,
            summary=summary.name if summary is not None else None,
            returncode=returncode,
            status=status_value,
        )
        return True

    async def get_status(self) -> dict[str, Optional[object]]:
        async with self._lock:
            running = self._process is not None and self._process.poll() is None
            summary_name = self._summary.name if self._summary is not None else None
            returncode = None if running else self._returncode
        current_state = manager.current_run_state()
        return {
            "running": running,
            "summary": summary_name or DEFAULT_SUMMARY,
            "returncode": returncode,
            "status": current_state.get("status", "na"),
            "hosts": manager.get_host_status_snapshot(),
        }

    async def _watch_process(self, process: subprocess.Popen[str], summary: Path) -> None:
        returncode = await asyncio.to_thread(process.wait)
        async with self._lock:
            if self._process is process:
                self._process = None
                self._returncode = returncode
        status_value: Optional[str]
        if returncode is None:
            status_value = None
        else:
            status_value = "pass" if returncode == 0 else "fail"
        await manager.broadcast_run_state(
            running=False,
            summary=summary.name,
            returncode=returncode,
            status=status_value,
        )

    @staticmethod
    def _terminate_process(process: subprocess.Popen[str]) -> int:
        try:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass
            finally:
                try:
                    process.wait(timeout=5)
                except Exception:
                    pass
        return process.poll() if process.poll() is not None else 0

    @staticmethod
    def _resolve_summary(summary_name: str) -> Path:
        candidate = Path(summary_name)
        if not candidate.is_absolute():
            candidate = SUMMARY_ROOT / candidate
        if not candidate.is_file():
            raise FileNotFoundError(f"Summary file not found: {candidate}")
        return candidate.resolve()


run_manager = RunManager()


@app.get("/documentation/index")
async def documentation_index() -> dict[str, list[dict[str, Optional[str]]]]:
    return {"entries": gather_doc_index()}


@app.get("/documentation/html/{component}")
async def documentation_html(component: str) -> HTMLResponse:
    entry = _locate_documentation_entry(component)
    if entry is None:
        raise HTTPException(status_code=404, detail="Document not found")
    html_path = entry["html_path"]
    if not isinstance(html_path, Path) or not html_path.is_file():
        raise HTTPException(status_code=404, detail="Document not found")
    content = html_path.read_text(encoding="utf-8")
    return HTMLResponse(
        content=content,
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": f'inline; filename="{html_path.name}"',
        },
    )


@app.get("/documentation/json/{component}", response_class=HTMLResponse)
async def documentation_json(component: str) -> HTMLResponse:
    entry = _locate_documentation_entry(component)
    if entry is None or entry.get("json_path") is None:
        raise HTTPException(status_code=404, detail="JSON document not found")
    json_path = entry["json_path"]
    if not isinstance(json_path, Path) or not json_path.is_file():
        raise HTTPException(status_code=404, detail="JSON document not found")
    try:
        raw_data = json_path.read_text(encoding="utf-8")
        parsed = json.loads(raw_data)
        formatted = json.dumps(parsed, indent=2, sort_keys=True)
    except Exception:
        return FileResponse(json_path, media_type="application/json", filename=json_path.name)
    escaped = html.escape(formatted)
    label = str(entry.get("label") or entry.get("component") or "Documentation")
    title = f"{label} JSON"
    content = f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
    <meta charset=\"utf-8\" />
    <title>{html.escape(title)}</title>
    <style>
        body {{
            margin: 0;
            padding: 2rem;
            font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
            background: #0f172a;
            color: #e2e8f0;
        }}
        main {{
            max-width: 960px;
            margin: 0 auto;
        }}
        h1 {{
            margin-bottom: 1.5rem;
            font-size: 1.6rem;
            letter-spacing: 0.05em;
        }}
        pre {{
            background: #111c3a;
            padding: 1.5rem;
            border-radius: 12px;
            overflow-x: auto;
            line-height: 1.5;
            font-size: 0.95rem;
        }}
    </style>
</head>
<body>
    <main>
        <h1>{html.escape(title)}</h1>
        <pre>{escaped}</pre>
    </main>
</body>
</html>
"""
    return HTMLResponse(content=content)


@app.get("/topology/url")
async def topology_url() -> JSONResponse:
    try:
        url = await asyncio.to_thread(build_topology_url)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - safeguard for unexpected failures
        raise HTTPException(status_code=500, detail=f"Failed to resolve topology URL: {exc}") from exc
    return JSONResponse({"url": url})


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    return HTMLResponse(INDEX_HTML)


@app.get("/latest")
async def latest() -> JSONResponse:
    return JSONResponse({"content": manager.latest})


@app.get("/coverage/latest")
async def coverage_latest_index() -> FileResponse:
    return _coverage_response("")


@app.get("/coverage/latest/{resource_path:path}")
async def coverage_latest_resource(resource_path: str) -> FileResponse:
    return _coverage_response(resource_path)


@app.get("/summaries")
async def summaries() -> JSONResponse:
    entries = discover_summary_files()
    default = DEFAULT_SUMMARY if DEFAULT_SUMMARY in entries else (entries[0] if entries else None)
    return JSONResponse({"entries": entries, "default": default})


@app.get("/config")
async def get_config() -> JSONResponse:
    state = await asyncio.to_thread(gather_config_state)
    await _refresh_host_monitor_from_settings(state.get("settings"))
    state["hosts"] = manager.get_host_status_snapshot()
    return JSONResponse(state)


@app.post("/config")
async def update_config(payload: ConfigUpdateRequest) -> JSONResponse:
    try:
        await asyncio.to_thread(
            update_test_configuration,
            payload.selected,
            test_coverage=payload.test_coverage,
            trace_http=payload.trace_http,
            verbose_level=payload.verbose_level,
            diff=payload.diff,
            gns3_server=payload.gns3_server,
            inventory=payload.inventory,
        )
    except FileNotFoundError as exc:
        return JSONResponse({"status": "error", "detail": str(exc)}, status_code=404)
    state = await asyncio.to_thread(gather_config_state)
    await _refresh_host_monitor_from_settings(state.get("settings"))
    state["hosts"] = manager.get_host_status_snapshot()
    state["status"] = "ok"
    return JSONResponse(state)


@app.post("/config/open")
async def open_config_file(payload: ConfigOpenRequest) -> JSONResponse:
    filename = payload.filename.strip()
    if not filename:
        raise HTTPException(status_code=400, detail="Filename is required")
    available = {path.name: path for path in discover_config_files()}
    target = available.get(filename)
    if target is None:
        raise HTTPException(status_code=404, detail="Config file not found")
    try:
        await asyncio.to_thread(_open_path_in_editor, target)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to open file: {exc}") from exc
    return JSONResponse({"status": "ok"})


@app.post("/host/shell", status_code=status.HTTP_202_ACCEPTED)
async def open_host_shell(payload: HostShellRequest) -> JSONResponse:
    host = payload.host.strip() if isinstance(payload.host, str) else ""
    await _launch_host_shell(host)
    return JSONResponse({"status": "launching"})


@app.get("/status")
async def status() -> JSONResponse:
    run_state = await run_manager.get_status()
    return JSONResponse(run_state)


@app.post("/control")
async def control(payload: ControlRequest) -> JSONResponse:
    action = payload.action.lower()
    if action == "start":
        summary_name = payload.summary or DEFAULT_SUMMARY
        try:
            resolved = await run_manager.start(summary_name)
        except FileNotFoundError as exc:
            return JSONResponse({"status": "error", "detail": str(exc)}, status_code=404)
        except RuntimeError as exc:
            return JSONResponse({"status": "error", "detail": str(exc)}, status_code=409)
        return JSONResponse({"status": "started", "summary": resolved.name})
    if action == "stop":
        stopped = await run_manager.stop()
        return JSONResponse({"status": "stopped" if stopped else "idle"})
    return JSONResponse({"status": "error", "detail": f"Unsupported action: {payload.action}"}, status_code=400)


@app.post("/update")
async def update_dashboard(payload: DashboardUpdate) -> JSONResponse:
    status_changed = manager.set_latest_dashboard(payload.content)
    await manager.broadcast_dashboard(payload.content)
    coverage_path = extract_coverage_report_path(payload.content)
    if coverage_path and manager.set_coverage_url(coverage_path):
        await manager.broadcast_coverage_url(manager.get_coverage_url())
    if status_changed is not None:
        state = manager.current_run_state()
        await manager.broadcast_run_state(
            running=bool(state.get("running", False)),
            summary=state.get("summary"),
            returncode=state.get("returncode"),
            status=status_changed,
        )
    return JSONResponse({"status": "ok"})


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
    except Exception:
        await manager.disconnect(websocket)


def main() -> None:
    """Run the dashboard server on port 4000."""
    uvicorn.run(app, host="0.0.0.0", port=4000, log_level="info")


if __name__ == "__main__":
    main()
