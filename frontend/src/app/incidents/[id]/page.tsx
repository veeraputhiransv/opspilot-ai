"use client";

import { useParams } from "next/navigation";

import { IncidentView } from "@/components/incident-view";

export default function IncidentPage() {
  const params = useParams<{ id: string }>();
  return <IncidentView id={params.id} />;
}
