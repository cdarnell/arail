{{/* k8s-lite Downward API helpers accepting a component name via dict: {Values: .Values, Component: "zeroclaw"} */}}
{{- define "k8s.downwardAPI.env" -}}
{{- $comp := index .Values .Component }}
{{- if $comp.downwardAPI.enabled }}
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

{{- define "k8s.downwardAPI.volumeMount" -}}
{{- $comp := index .Values .Component }}
{{- if $comp.downwardAPI.enabled }}
- name: podinfo
  mountPath: {{ $comp.downwardAPI.mountPath | default "/etc/podinfo" }}
  readOnly: true
{{- end }}
{{- end }}

{{- define "k8s.downwardAPI.volume" -}}
{{- $comp := index .Values .Component }}
{{- if $comp.downwardAPI.enabled }}
- name: podinfo
  downwardAPI:
    items:
      - path: "labels"
        fieldRef:
          fieldPath: metadata.labels
{{- end }}
{{- end }}
