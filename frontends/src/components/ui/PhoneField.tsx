"use client";

import * as React from "react";
import PhoneInputBase, { type Country } from "react-phone-number-input";
import "react-phone-number-input/style.css";
import "./phone-field.css";
import { cn } from "@/lib/utils";

// Re-export the validators so forms import every phone helper from one place.
export { isValidPhoneNumber, isPossiblePhoneNumber } from "react-phone-number-input";

export interface PhoneFieldProps {
  /** E.164 phone value, e.g. "+94771234567". */
  value: string;
  /** Receives the E.164 value ("" when the field is cleared). */
  onChange: (value: string) => void;
  /** Fires with the selected ISO country code (e.g. "LK") when it changes. */
  onCountryChange?: (country: Country | undefined) => void;
  /** Country selected before the user types a "+" calling code. */
  defaultCountry?: Country;
  placeholder?: string;
  disabled?: boolean;
  /** Render the invalid (red) state. */
  error?: boolean;
  id?: string;
  name?: string;
  className?: string;
}

/**
 * International phone input with a country-code selector and libphonenumber
 * validation. Emits its value in E.164 format. Pair with the exported
 * `isValidPhoneNumber` helper to validate on submit.
 */
export function PhoneField({
  value,
  onChange,
  onCountryChange,
  defaultCountry = "LK",
  placeholder = "Enter phone number",
  disabled,
  error,
  id,
  name,
  className,
}: PhoneFieldProps) {
  return (
    <PhoneInputBase
      international
      countryCallingCodeEditable={false}
      defaultCountry={defaultCountry}
      value={value || undefined}
      onChange={(v) => onChange(v ?? "")}
      onCountryChange={onCountryChange}
      disabled={disabled}
      placeholder={placeholder}
      id={id}
      name={name}
      numberInputProps={{ autoComplete: "tel" }}
      className={cn(
        "phone-field",
        error && "phone-field--error",
        disabled && "phone-field--disabled",
        className
      )}
    />
  );
}
