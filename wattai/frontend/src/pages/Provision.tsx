import { useState } from "react";
import { MapPin, Wifi, CheckCircle, Bluetooth } from "lucide-react";
import api from "../lib/api";

const STEPS = ["Location", "Connect meter", "Configure", "Done"];

function StepDot({ index, active, done }: { index: number; active: boolean; done: boolean }) {
  return (
    <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium transition-colors ${
      done ? "bg-violet-600 text-white" : active ? "bg-violet-100 text-violet-700 border-2 border-violet-400" : "bg-gray-100 text-gray-400"
    }`}>
      {done ? <CheckCircle size={16} /> : index + 1}
    </div>
  );
}

export default function Provision() {
  const [step, setStep] = useState(0);
  const [form, setForm] = useState({
    country: "", city: "", timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    currency: "USD", serial: "", model: "SPM01", location_label: "Main panel",
    flat_rate: "0.10",
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const update = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }));

  async function submit() {
    setLoading(true);
    setError("");
    try {
      await api.post("/provisioning/complete", {
        serial_number: form.serial,
        model: form.model,
        location_label: form.location_label,
        mqtt_topic_prefix: `${form.model}/${form.serial}`,
        localization: {
          country: form.country,
          city: form.city,
          timezone: form.timezone,
          currency: form.currency,
          tariff_type: "flat",
          flat_rate: parseFloat(form.flat_rate),
        },
      });
      setStep(3);
    } catch (e: any) {
      setError(e.response?.data?.detail ?? "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="max-w-lg mx-auto p-6">
      <h1 className="text-xl font-medium text-gray-800 mb-6">Add a meter</h1>

      {/* Step indicators */}
      <div className="flex items-center gap-2 mb-8">
        {STEPS.map((label, i) => (
          <div key={i} className="flex items-center gap-2">
            <StepDot index={i} active={step === i} done={step > i} />
            <span className={`text-xs ${step === i ? "text-gray-700 font-medium" : "text-gray-400"}`}>{label}</span>
            {i < STEPS.length - 1 && <div className="w-8 h-px bg-gray-200" />}
          </div>
        ))}
      </div>

      {/* Step 0 — Location */}
      {step === 0 && (
        <div className="space-y-4">
          <div className="flex items-center gap-2 mb-2 text-gray-500"><MapPin size={16} /> <span className="text-sm">Where is this meter installed?</span></div>
          {[["country", "Country"], ["city", "City"], ["currency", "Currency code (e.g. SAR, USD, AED)"]].map(([k, label]) => (
            <div key={k}>
              <label className="block text-xs text-gray-500 mb-1">{label}</label>
              <input className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
                value={(form as any)[k]} onChange={(e) => update(k, e.target.value)} />
            </div>
          ))}
          <div>
            <label className="block text-xs text-gray-500 mb-1">Flat electricity rate (per kWh)</label>
            <input type="number" step="0.001" className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
              value={form.flat_rate} onChange={(e) => update("flat_rate", e.target.value)} />
          </div>
          <button onClick={() => setStep(1)}
            className="w-full bg-violet-600 text-white rounded-lg py-2 text-sm hover:bg-violet-700">
            Continue
          </button>
        </div>
      )}

      {/* Step 1 — Connect */}
      {step === 1 && (
        <div className="space-y-4">
          <div className="flex items-center gap-2 mb-2 text-gray-500"><Bluetooth size={16} /><span className="text-sm">Connect to your meter via BLE</span></div>
          <div className="bg-blue-50 border border-blue-100 rounded-xl p-4 text-sm text-blue-700 space-y-1">
            <p>1. Power on the meter (LED blinks).</p>
            <p>2. Open your phone's Bluetooth settings and pair with <strong>SPM-{"{serial}"}</strong> or <strong>SDM-{"{serial}"}</strong>.</p>
            <p>3. Default BLE password: <code className="bg-blue-100 px-1 rounded">1234</code></p>
            <p>4. Use the BLE commands to set WiFi and MQTT credentials (see docs).</p>
            <p>5. Once the meter connects, enter its serial number below.</p>
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Serial number (from meter label)</label>
            <input className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm font-mono"
              placeholder="18132672040792" value={form.serial} onChange={(e) => update("serial", e.target.value)} />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Model</label>
            <select className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
              value={form.model} onChange={(e) => update("model", e.target.value)}>
              <option>SPM01</option>
              <option>SPM02</option>
              <option>SDM01</option>
            </select>
          </div>
          <button onClick={() => setStep(2)} disabled={!form.serial}
            className="w-full bg-violet-600 text-white rounded-lg py-2 text-sm hover:bg-violet-700 disabled:opacity-40">
            Continue
          </button>
        </div>
      )}

      {/* Step 2 — Confirm */}
      {step === 2 && (
        <div className="space-y-4">
          <div className="flex items-center gap-2 mb-2 text-gray-500"><Wifi size={16} /><span className="text-sm">Confirm and save</span></div>
          <div className="bg-gray-50 rounded-xl p-4 text-sm space-y-1">
            <p><span className="text-gray-400">Serial:</span> {form.serial}</p>
            <p><span className="text-gray-400">Model:</span> {form.model}</p>
            <p><span className="text-gray-400">Location:</span> {form.location_label}</p>
            <p><span className="text-gray-400">Country:</span> {form.country} / {form.city}</p>
            <p><span className="text-gray-400">Currency:</span> {form.currency}</p>
            <p><span className="text-gray-400">Rate:</span> {form.flat_rate} / kWh</p>
          </div>
          {error && <p className="text-red-500 text-xs">{error}</p>}
          <button onClick={submit} disabled={loading}
            className="w-full bg-violet-600 text-white rounded-lg py-2 text-sm hover:bg-violet-700 disabled:opacity-40">
            {loading ? "Saving…" : "Save and finish"}
          </button>
        </div>
      )}

      {/* Step 3 — Done */}
      {step === 3 && (
        <div className="text-center py-8">
          <CheckCircle className="mx-auto mb-4 text-green-500" size={48} />
          <p className="text-lg font-medium text-gray-800">Meter registered</p>
          <p className="text-sm text-gray-500 mt-1">Readings will appear on your dashboard within one interval cycle.</p>
          <a href="/" className="mt-6 inline-block bg-violet-600 text-white rounded-lg px-6 py-2 text-sm hover:bg-violet-700">
            Go to dashboard
          </a>
        </div>
      )}
    </div>
  );
}
