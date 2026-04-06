"use client";

import { ReactNode } from "react";
import { useSubscription } from "@/context/AuthContext";
import { UpgradeBanner } from "./UpgradeBanner";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

export function SubscriberGate({ children, fallback }: Props) {
  const { isSubscriber } = useSubscription();
  if (isSubscriber) return <>{children}</>;
  return <>{fallback ?? <UpgradeBanner />}</>;
}
