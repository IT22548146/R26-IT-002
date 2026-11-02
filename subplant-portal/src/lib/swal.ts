/**
 * Drop-in replacement for sweetalert2 that routes everything to bottom-right
 * toasts (see components/Toast.tsx). Import as the default export in place of
 * `sweetalert2` and existing `Swal.fire({...})` calls keep working:
 *
 *   import Swal from "@/lib/swal";
 *   Swal.fire({ icon: "success", title: "Saved" });
 *   const r = await Swal.fire({ ..., showCancelButton: true });
 *   if (r.isConfirmed) { ... }
 */
import { toast } from "@/components/Toast";

type SwalIcon = "success" | "error" | "warning" | "info" | "question";

interface SwalOptions {
  icon?: SwalIcon;
  title?: string;
  text?: string;
  html?: string;
  showCancelButton?: boolean;
  confirmButtonText?: string;
  cancelButtonText?: string;
  confirmButtonColor?: string;
  // Tolerate any other sweetalert2 option that legacy call sites still pass.
  [key: string]: any;
}

interface SwalResult {
  isConfirmed: boolean;
  isDismissed: boolean;
}

// Turn simple HTML (used in a few legacy calls) into plain, multi-line text.
function htmlToText(html: string): string {
  return html
    .replace(/<\s*br\s*\/?\s*>/gi, "\n")
    .replace(/<\/(p|div|li)>/gi, "\n")
    .replace(/<[^>]+>/g, "")
    .replace(/&nbsp;/gi, " ")
    .replace(/&amp;/gi, "&")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

const toastFor = (icon: SwalIcon | undefined, message: string, title?: string) => {
  switch (icon) {
    case "success": return toast.success(message, title);
    case "error":   return toast.error(message, title);
    case "warning": return toast.warning(message, title);
    default:        return toast.info(message, title);
  }
};

async function fire(options: SwalOptions | string = {}): Promise<SwalResult> {
  const opts: SwalOptions = typeof options === "string" ? { title: options } : options || {};

  const body = opts.text || (opts.html ? htmlToText(opts.html) : "");

  // Confirmation dialog → confirm-style toast with buttons.
  if (opts.showCancelButton) {
    const danger = /#(dc2626|d33|ef4444|e3342f|b91c1c)/i.test(opts.confirmButtonColor || "");
    const confirmed = await toast.confirm({
      title: opts.title,
      message: body,
      confirmText: opts.confirmButtonText || "Confirm",
      cancelText: opts.cancelButtonText || "Cancel",
      danger,
    });
    return { isConfirmed: confirmed, isDismissed: !confirmed };
  }

  // Plain notification. Prefer the reason (text/html) as the message so error
  // toasts always show the specific cause; keep the title as a heading.
  if (body) {
    toastFor(opts.icon, body, opts.title);
  } else {
    toastFor(opts.icon, opts.title || "");
  }
  return { isConfirmed: true, isDismissed: false };
}

const Swal = { fire };
export default Swal;
