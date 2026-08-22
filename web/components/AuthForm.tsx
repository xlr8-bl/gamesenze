"use client";

import { useState } from "react";
import { Eye, EyeSlash } from "@phosphor-icons/react";
import { Notice } from "./ui";

/**
 * The sign-in and sign-up form.
 *
 * The fields, states and validation are real; the submit is not wired to an
 * identity provider yet, and the form says so rather than pretending to sign
 * anyone in. Every label sits above its input, errors appear under the field
 * they belong to and are wired with aria-describedby, and validation runs on
 * blur rather than on every keystroke.
 */
export default function AuthForm({ mode }: { mode: "signin" | "signup" }) {
  const signup = mode === "signup";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [touched, setTouched] = useState<Record<string, boolean>>({});
  const [submitted, setSubmitted] = useState(false);

  const emailError =
    touched.email && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)
      ? "Enter an email address in the form name@example.com."
      : null;
  const passwordError =
    touched.password && password.length < 10
      ? "Use at least 10 characters. Length beats symbols."
      : null;
  const valid = !emailError && !passwordError && email && password.length >= 10;

  return (
    <form
      className="panel panel-pad stack"
      style={{ gap: "var(--s-4)" }}
      onSubmit={(e) => {
        e.preventDefault();
        setTouched({ email: true, password: true });
        if (valid) setSubmitted(true);
      }}
      noValidate
    >
      <Field
        id="email"
        label="Email address"
        type="email"
        value={email}
        autoComplete="email"
        error={emailError}
        onChange={setEmail}
        onBlur={() => setTouched((t) => ({ ...t, email: true }))}
      />

      <div>
        <label htmlFor="password" className="label" style={{ display: "block", marginBottom: 6 }}>
          Password
        </label>
        <div style={{ position: "relative" }}>
          <input
            id="password"
            className="input"
            type={show ? "text" : "password"}
            value={password}
            autoComplete={signup ? "new-password" : "current-password"}
            aria-invalid={Boolean(passwordError)}
            aria-describedby={passwordError ? "password-error" : signup ? "password-hint" : undefined}
            onChange={(e) => setPassword(e.target.value)}
            onBlur={() => setTouched((t) => ({ ...t, password: true }))}
            style={{ paddingRight: 48 }}
          />
          <button
            type="button"
            className="btn btn-quiet"
            aria-label={show ? "Hide password" : "Show password"}
            onClick={() => setShow((v) => !v)}
            style={{ position: "absolute", right: 4, top: 4, minHeight: 40, padding: "0 10px" }}
          >
            {show ? <EyeSlash size={17} weight="bold" /> : <Eye size={17} weight="bold" />}
          </button>
        </div>
        {passwordError ? (
          <p id="password-error" className="field-error">{passwordError}</p>
        ) : signup ? (
          <p id="password-hint" className="field-hint">At least 10 characters.</p>
        ) : null}
      </div>

      {signup && (
        <label className="cluster" style={{ gap: "var(--s-3)", alignItems: "flex-start", flexWrap: "nowrap" }}>
          <input type="checkbox" required className="check" />
          <span style={{ fontSize: "var(--t-small)", color: "var(--ink-2)" }}>
            I am 18 or over, and I have read the{" "}
            <a href="/terms/">terms of service</a> and the{" "}
            <a href="/responsible-gambling/">responsible gambling</a> page.
          </span>
        </label>
      )}

      <button type="submit" className="btn" style={{ width: "100%" }}>
        {signup ? "Create account" : "Sign in"}
      </button>

      {submitted && (
        <Notice tone="caution">
          Accounts are not open yet. Nothing was sent and no account was
          created. The form is here so the flow can be reviewed before it is
          wired to anything.
        </Notice>
      )}

      <p style={{ fontSize: "var(--t-small)", color: "var(--ink-3)", marginBottom: 0 }}>
        {signup ? (
          <>
            Already have an account? <a href="/signin/">Sign in</a>.
          </>
        ) : (
          <>
            No account yet? <a href="/signup/">Create one</a>.
          </>
        )}
      </p>
    </form>
  );
}

function Field({
  id,
  label,
  type,
  value,
  error,
  autoComplete,
  onChange,
  onBlur,
}: {
  id: string;
  label: string;
  type: string;
  value: string;
  error: string | null;
  autoComplete?: string;
  onChange: (v: string) => void;
  onBlur: () => void;
}) {
  return (
    <div>
      <label htmlFor={id} className="label" style={{ display: "block", marginBottom: 6 }}>
        {label}
      </label>
      <input
        id={id}
        className="input"
        type={type}
        value={value}
        autoComplete={autoComplete}
        aria-invalid={Boolean(error)}
        aria-describedby={error ? `${id}-error` : undefined}
        onChange={(e) => onChange(e.target.value)}
        onBlur={onBlur}
      />
      {error && <p id={`${id}-error`} className="field-error">{error}</p>}
    </div>
  );
}
