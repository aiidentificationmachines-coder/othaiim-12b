/**
 * traffic_observer_frontend_hook.ts
 * Iconic Workflow — AIIM Traffic Observer Client Hook
 * Othaiim LLC · USPTO 1135-11714-1 · Patent Pending
 *
 * Complete production-ready React client-side hook that:
 * 1. Tracks page views automatically on route changes.
 * 2. Manages secure sessionId in sessionStorage.
 * 3. Dispatches interaction telemetry seamlessly to trafficObserverEngine.
 * 4. Integrates seamlessly with AI assistant rating and edit-delta streams.
 * 5. Fails gracefully and silently in production to protect UX.
 */

import { useEffect, useCallback } from "react";

// Types representing the configuration and payload of the observer
export interface UserIdentity {
  userId?: string;
  userEmail: string;
  userRole?: string;
  dealerId?: string;
}

export interface TrackingEvent {
  eventType: "PAGE_VIEW" | "CLICK" | "AI_QUERY" | "AI_RATING" | "FORM_SUBMIT" | "NAVIGATION" | "SEARCH" | "SESSION_START" | "SESSION_END";
  pageName: string;
  pageUrl?: string;
  elementId?: string;
  elementType?: string;
  inputValue?: string;
  aiQuery?: string;
  aiResponse?: string;
  aiRating?: number;
  aiEditDelta?: number;
  aiIntentType?: string;
  arScore?: number;
  prScore?: number;
  srScore?: number;
  responseMs?: number;
}

const ENGINE_ENDPOINT = "/api/functions/trafficObserverEngine";

export function useTrafficObserver(user: UserIdentity | null, currentPageName: string) {
  
  // Safe helper to obtain or establish session IDs
  const getOrInitializeSessionId = (): string => {
    try {
      let sessId = sessionStorage.getItem("iconic_observer_session_id");
      if (!sessId) {
        sessId = `sess_${Date.now()}_${Math.random().toString(36).substring(2, 11)}`;
        sessionStorage.setItem("iconic_observer_session_id", sessId);
      }
      return sessId;
    } catch {
      return `sess_fallback_${Date.now()}`;
    }
  };

  // The primary transmission mechanism to send telemetry to the backend engine
  const trackEvent = useCallback(async (eventDetail: TrackingEvent) => {
    if (!user || !user.userEmail) {
      // Silently discard tracking requests if user is not resolved
      return;
    }

    try {
      const sessionId = getOrInitializeSessionId();
      
      const payload = {
        mode: "INGEST",
        // Identity Metadata
        userId: user.userId || null,
        userEmail: user.userEmail,
        userRole: user.userRole || "unknown",
        dealerId: user.dealerId || "unknown",
        sessionId,
        // Event Core Metrics
        eventType: eventDetail.eventType,
        pageName: eventDetail.pageName,
        pageUrl: eventDetail.pageUrl || (typeof window !== "undefined" ? window.location.href : ""),
        elementId: eventDetail.elementId || null,
        elementType: eventDetail.elementType || null,
        inputValue: eventDetail.inputValue || null,
        deviceType: typeof window !== "undefined" && window.innerWidth < 768 ? "mobile" : "desktop",
        referrer: typeof document !== "undefined" ? document.referrer : null,
        // AI Integration
        aiQuery: eventDetail.aiQuery || null,
        aiResponse: eventDetail.aiResponse || null,
        aiRating: eventDetail.aiRating || null,
        aiEditDelta: eventDetail.aiEditDelta !== undefined ? eventDetail.aiEditDelta : null,
        aiIntentType: eventDetail.aiIntentType || null,
        responseMs: eventDetail.responseMs || null,
        // RSI Integration Scores
        arScore: eventDetail.arScore || null,
        prScore: eventDetail.prScore || null,
        srScore: eventDetail.srScore || null,
      };

      // Fire and forget transmission to ensure no thread blocking
      await fetch(ENGINE_ENDPOINT, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });
    } catch (e) {
      // Fail silently in production. Telemetry must never interrupt the core workflows.
      console.warn("TrafficObserver transmission failure protected:", e);
    }
  }, [user]);

  // Hook 1: Auto-Track Page Views on route changes or component updates
  useEffect(() => {
    if (user && user.userEmail && currentPageName) {
      trackEvent({
        eventType: "PAGE_VIEW",
        pageName: currentPageName,
        pageUrl: typeof window !== "undefined" ? window.location.href : "",
      });
    }
  }, [currentPageName, user, trackEvent]);

  // Hook 2: Helper wiring for capturing AI Assistant Ratings directly from feedback UI components
  const trackAiRating = useCallback((params: {
    query: string;
    response: string;
    rating: number; // Scale of 1 to 5
    editDelta?: number; // 0 to 100 percentage delta
    intentType?: string;
    responseMs?: number;
  }) => {
    trackEvent({
      eventType: "AI_RATING",
      pageName: currentPageName,
      aiQuery: params.query,
      aiResponse: params.response,
      aiRating: params.rating,
      aiEditDelta: params.editDelta ?? 0,
      aiIntentType: params.intentType || "general",
      responseMs: params.responseMs,
    });
  }, [currentPageName, trackEvent]);

  // Hook 3: Helper wiring for manual component/button click tracking
  const trackClick = useCallback((elementId: string, elementType: string = "button", additionalData?: string) => {
    trackEvent({
      eventType: "CLICK",
      pageName: currentPageName,
      elementId,
      elementType,
      inputValue: additionalData,
    });
  }, [currentPageName, trackEvent]);

  return {
    trackEvent,
    trackAiRating,
    trackClick,
    sessionId: user ? getOrInitializeSessionId() : null,
  };
}
