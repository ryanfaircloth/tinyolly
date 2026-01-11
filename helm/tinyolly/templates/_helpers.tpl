{{/*
Common labels
*/}}
{{- define "tinyolly.labels" -}}
helm.sh/chart: {{ include "tinyolly.chart" . }}
{{ include "tinyolly.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- with .Values.commonLabels }}
{{ toYaml . }}
{{- end }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "tinyolly.selectorLabels" -}}
app.kubernetes.io/name: {{ include "tinyolly.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "tinyolly.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Expand the name of the chart.
*/}}
{{- define "tinyolly.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "tinyolly.fullname" -}}
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
UI component name
*/}}
{{- define "tinyolly.ui.name" -}}
{{ include "tinyolly.fullname" . }}-ui
{{- end }}

{{/*
UI service account name
*/}}
{{- define "tinyolly.ui.serviceAccountName" -}}
{{- if .Values.ui.serviceAccount.create }}
{{- default (include "tinyolly.ui.name" .) .Values.ui.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.ui.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
UI component labels
*/}}
{{- define "tinyolly.ui.labels" -}}
{{ include "tinyolly.labels" . }}
app.kubernetes.io/component: ui
{{- end }}

{{/*
UI selector labels
*/}}
{{- define "tinyolly.ui.selectorLabels" -}}
{{ include "tinyolly.selectorLabels" . }}
app.kubernetes.io/component: ui
app: tinyolly-ui
{{- end }}

{{/*
OpAMP Server component name
*/}}
{{- define "tinyolly.opampServer.name" -}}
{{ include "tinyolly.fullname" . }}-opamp-server
{{- end }}

{{/*
OpAMP Server service account name
*/}}
{{- define "tinyolly.opampServer.serviceAccountName" -}}
{{- if .Values.opampServer.serviceAccount.create }}
{{- default (include "tinyolly.opampServer.name" .) .Values.opampServer.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.opampServer.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
OpAMP Server component labels
*/}}
{{- define "tinyolly.opampServer.labels" -}}
{{ include "tinyolly.labels" . }}
app.kubernetes.io/component: opamp-server
{{- end }}

{{/*
OpAMP Server selector labels
*/}}
{{- define "tinyolly.opampServer.selectorLabels" -}}
{{ include "tinyolly.selectorLabels" . }}
app.kubernetes.io/component: opamp-server
app: tinyolly-opamp-server
{{- end }}

{{/*
OTLP Receiver component name
*/}}
{{- define "tinyolly.otlpReceiver.name" -}}
{{ include "tinyolly.fullname" . }}-otlp-receiver
{{- end }}

{{/*
OTLP Receiver service account name
*/}}
{{- define "tinyolly.otlpReceiver.serviceAccountName" -}}
{{- if .Values.otlpReceiver.serviceAccount.create }}
{{- default (include "tinyolly.otlpReceiver.name" .) .Values.otlpReceiver.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.otlpReceiver.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
OTLP Receiver component labels
*/}}
{{- define "tinyolly.otlpReceiver.labels" -}}
{{ include "tinyolly.labels" . }}
app.kubernetes.io/component: otlp-receiver
{{- end }}

{{/*
OTLP Receiver selector labels
*/}}
{{- define "tinyolly.otlpReceiver.selectorLabels" -}}
{{ include "tinyolly.selectorLabels" . }}
app.kubernetes.io/component: otlp-receiver
app: tinyolly-otlp-receiver
{{- end }}

{{/*
OTel Collector Supervisor component name
*/}}
{{- define "tinyolly.otelCollectorSupervisor.name" -}}
{{ include "tinyolly.fullname" . }}-otel-collector
{{- end }}

{{/*
OTel Collector Supervisor service account name
*/}}
{{- define "tinyolly.otelCollectorSupervisor.serviceAccountName" -}}
{{- if .Values.otelCollectorSupervisor.serviceAccount.create }}
{{- default (include "tinyolly.otelCollectorSupervisor.name" .) .Values.otelCollectorSupervisor.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.otelCollectorSupervisor.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
OTel Collector Supervisor component labels
*/}}
{{- define "tinyolly.otelCollectorSupervisor.labels" -}}
{{ include "tinyolly.labels" . }}
app.kubernetes.io/component: otel-collector
{{- end }}

{{/*
OTel Collector Supervisor selector labels
*/}}
{{- define "tinyolly.otelCollectorSupervisor.selectorLabels" -}}
{{ include "tinyolly.selectorLabels" . }}
app.kubernetes.io/component: otel-collector
app: otel-collector
{{- end }}

{{/*
Image pull policy helper
Usage: include "tinyolly.imagePullPolicy" (dict "component" .Values.ui.image "global" .)
*/}}
{{- define "tinyolly.imagePullPolicy" -}}
{{- if .component.pullPolicy -}}
{{- .component.pullPolicy -}}
{{- else -}}
{{- .global.Values.image.pullPolicy -}}
{{- end -}}
{{- end }}
