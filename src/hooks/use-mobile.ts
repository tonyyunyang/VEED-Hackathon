import * as React from "react";

const MOBILE_BREAKPOINT = 768;

export function useIsMobile(): boolean {
  const getMatches = React.useCallback(() => {
    if (typeof window === "undefined") {
      return false;
    }
    return window.innerWidth < MOBILE_BREAKPOINT;
  }, []);

  const [isMobile, setIsMobile] = React.useState(getMatches);

  React.useEffect(() => {
    if (typeof window === "undefined") {
      return undefined;
    }

    const mediaQuery = window.matchMedia(
      `(max-width: ${MOBILE_BREAKPOINT - 1}px)`,
    );

    const onChange = () => {
      setIsMobile(mediaQuery.matches);
    };

    onChange();
    mediaQuery.addEventListener("change", onChange);

    return () => {
      mediaQuery.removeEventListener("change", onChange);
    };
  }, [getMatches]);

  return isMobile;
}
