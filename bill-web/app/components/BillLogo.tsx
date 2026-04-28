import Image from "next/image";

export function BillLogo() {
  return (
    <div className="flex items-center gap-3">
      <Image src="/logo.png" alt="Bill Operations" width={40} height={40} className="shrink-0" />
      <div className="leading-tight">
        <p className="text-sm font-bold uppercase tracking-[0.15em] text-slate-50">Bill Operations</p>
        <p className="text-[11px] tracking-wide text-slate-400">Command Center</p>
      </div>
    </div>
  );
}
