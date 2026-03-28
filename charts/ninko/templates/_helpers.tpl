{{/*
Expand the name of the chart.
*/}}
{{- define "ninko.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
Truncate at 63 chars because some Kubernetes name fields are limited to this.
*/}}
{{- define "ninko.fullname" -}}
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
{{- define "ninko.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels applied to all resources.
*/}}
{{- define "ninko.labels" -}}
helm.sh/chart: {{ include "ninko.chart" . }}
{{ include "ninko.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: ninko
{{- end }}

{{/*
Selector labels – stable, must not change between upgrades.
*/}}
{{- define "ninko.selectorLabels" -}}
app.kubernetes.io/name: {{ include "ninko.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
ServiceAccount name.
*/}}
{{- define "ninko.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "ninko.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Namespace – use .Values.namespace, fall back to release namespace.
*/}}
{{- define "ninko.namespace" -}}
{{- default .Release.Namespace .Values.namespace }}
{{- end }}

{{/*
Component-specific fullnames.
*/}}
{{- define "ninko.backend.fullname" -}}
{{- printf "%s-backend" (include "ninko.fullname" .) }}
{{- end }}

{{- define "ninko.redis.fullname" -}}
{{- printf "%s-redis" (include "ninko.fullname" .) }}
{{- end }}

{{- define "ninko.chromadb.fullname" -}}
{{- printf "%s-chromadb" (include "ninko.fullname" .) }}
{{- end }}

{{- define "ninko.searxng.fullname" -}}
{{- printf "%s-searxng" (include "ninko.fullname" .) }}
{{- end }}
