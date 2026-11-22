import React from "react";
import { getModule, getSubPage } from "../catalog/navigation";
import { ModulePageProps } from "./CommandModulePage";
import { FinanceView } from "../components/OpsViews";
import { PageHeader, ResponsiveWorkspace } from "../components/ui/DesignSystem";

export default function FinanceModulePage({ subPage, onSelectSubPage }: ModulePageProps) {
  const mod = getModule("finance");
  const page = getSubPage("finance", subPage);

  return (
    <ResponsiveWorkspace subPages={mod.subPages} activeSubPage={page.id} onSelectSubPage={onSelectSubPage}>
      <PageHeader
        eyebrow="FINANCE CENTRE // TREASURY & PCI GUARD"
        title={page.label}
        description={page.description}
      />
      <FinanceView />
    </ResponsiveWorkspace>
  );
}
