{{/* Nucleus Downward API helpers
  Developer note: when adding new templates that need pod metadata, include these helpers
  to keep Downward API mounts and envs consistent across charts. */}}
{{- define "nucleus.downwardAPI.env" -}}
{{- if .Values.agentEscalator.downwardAPI.enabled }}
- name: POD_NAME
  valueFrom:
    fieldRef:
      fieldPath: metadata.name
- name: POD_NAMESPACE
  valueFrom:
    fieldRef:
      fieldPath: metadata.namespace
{{- end }}
{{- end }}

{{- define "nucleus.downwardAPI.volumeMount" -}}
{{- if .Values.agentEscalator.downwardAPI.enabled }}
- name: podinfo
  mountPath: {{ .Values.agentEscalator.downwardAPI.mountPath | default "/etc/podinfo" }}
  readOnly: true
{{- end }}
{{- end }}

{{- define "nucleus.downwardAPI.volume" -}}
{{- if .Values.agentEscalator.downwardAPI.enabled }}
volumes:
- name: podinfo
  downwardAPI:
    items:
      - path: "labels"
        fieldRef:
          fieldPath: metadata.labels
{{- end }}
{{- end }}
{{/*
Expand the name of the chart.
*/}}
{{- define "minimalist.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "minimalist.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "minimalist.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "minimalist.labels" -}}
helm.sh/chart: {{ include "minimalist.chart" . }}
{{ include "minimalist.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "minimalist.selectorLabels" -}}
app.kubernetes.io/name: {{ include "minimalist.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "minimalist.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "minimalist.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}
