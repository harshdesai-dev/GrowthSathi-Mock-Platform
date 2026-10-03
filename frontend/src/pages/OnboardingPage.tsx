import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate } from "react-router-dom";

import growthSathiLogo from "../assets/brand/growthsathi-logo.webp";
import type { ProfileInput } from "../api/client";
import { useAuth } from "../auth/auth-context";

function isIndianMobile(value: string) {
  const compact = value.replace(/[\s\-()]/g, "");
  return /^(?:\+91|91|0)?[6-9]\d{9}$/.test(compact);
}

export function OnboardingPage() {
  const { user, getProfile, saveProfile } = useAuth();
  const navigate = useNavigate();
  const [isLoading, setIsLoading] = useState(true);
  const [submitError, setSubmitError] = useState("");
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<ProfileInput>({
    defaultValues: {
      full_name: user?.full_name ?? "",
      phone: "",
      class_level: undefined,
      target_exam: undefined,
    },
  });

  useEffect(() => {
    let active = true;
    void getProfile()
      .then((profile) => {
        if (!active) return;
        reset({
          full_name: profile.full_name || user?.full_name || "",
          phone: profile.phone,
          class_level: profile.class_level || undefined,
          target_exam: profile.target_exam || undefined,
        });
      })
      .catch((error) => {
        if (active)
          setSubmitError(
            error instanceof Error ? error.message : "Profile unavailable.",
          );
      })
      .finally(() => {
        if (active) setIsLoading(false);
      });
    return () => {
      active = false;
    };
  }, [getProfile, reset, user?.full_name]);

  const onSubmit = async (values: ProfileInput) => {
    setSubmitError("");
    try {
      await saveProfile(values);
      navigate("/dashboard", { replace: true });
    } catch (error) {
      setSubmitError(
        error instanceof Error
          ? error.message
          : "Your profile could not be saved.",
      );
    }
  };

  return (
    <main className="onboarding-shell">
      <section className="onboarding-card" aria-labelledby="onboarding-title">
        <header className="form-header">
          <img src={growthSathiLogo} alt="GrowthSathi" width="64" height="64" />
          <div>
            <p className="eyebrow">One quick step</p>
            <h1 id="onboarding-title">Build your student profile</h1>
          </div>
        </header>
        <p className="form-intro">
          Tell us what you are preparing for. You can update this later.
        </p>

        {isLoading ? (
          <p className="status-message" aria-busy="true">
            Loading your profile…
          </p>
        ) : (
          <form
            className="profile-form"
            onSubmit={handleSubmit(onSubmit)}
            noValidate
          >
            <label>
              <span>Full name</span>
              <input
                autoComplete="name"
                {...register("full_name", {
                  required: "Full name is required.",
                  validate: (value) =>
                    value.trim().length >= 2 || "Enter your full name.",
                })}
              />
              {errors.full_name ? (
                <small role="alert">{errors.full_name.message}</small>
              ) : null}
            </label>

            <label>
              <span>Email</span>
              <input value={user?.email ?? ""} readOnly aria-readonly="true" />
            </label>

            <label>
              <span>Indian mobile number</span>
              <input
                inputMode="tel"
                autoComplete="tel"
                placeholder="98765 43210"
                {...register("phone", {
                  required: "Phone number is required.",
                  validate: (value) =>
                    isIndianMobile(value) ||
                    "Enter a valid 10-digit Indian mobile number.",
                })}
              />
              {errors.phone ? (
                <small role="alert">{errors.phone.message}</small>
              ) : null}
            </label>

            <label>
              <span>Class</span>
              <select
                {...register("class_level", { required: "Select your class." })}
              >
                <option value="">Select class</option>
                <option value="11">11th</option>
                <option value="12">12th</option>
                <option value="DROPPER">Dropper</option>
              </select>
              {errors.class_level ? (
                <small role="alert">{errors.class_level.message}</small>
              ) : null}
            </label>

            <fieldset>
              <legend>Preparing for</legend>
              <div className="choice-grid">
                {[
                  ["JEE", "JEE Main"],
                  ["CET", "MHT-CET"],
                  ["BOTH", "Both"],
                ].map(([value, label]) => (
                  <label className="choice" key={value}>
                    <input
                      type="radio"
                      value={value}
                      {...register("target_exam", {
                        required: "Choose a target exam.",
                      })}
                    />
                    <span>{label}</span>
                  </label>
                ))}
              </div>
              {errors.target_exam ? (
                <small role="alert">{errors.target_exam.message}</small>
              ) : null}
            </fieldset>

            {submitError ? (
              <p className="form-error" role="alert">
                {submitError}
              </p>
            ) : null}
            <button
              className="primary-button"
              type="submit"
              disabled={isSubmitting}
            >
              {isSubmitting ? "Saving profile…" : "Continue to dashboard"}
            </button>
          </form>
        )}
      </section>
    </main>
  );
}
