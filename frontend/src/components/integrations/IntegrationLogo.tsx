import React from "react";

interface IntegrationLogoProps {
  id: string;
  size?: number;
}

/**
 * Crisp, recognizable official-style vector SVG brand logos for every ULTRON integration.
 * Zero external CDN image requests (zero broken icons offline or under strict CSP).
 */
export function IntegrationLogo({ id, size = 28 }: IntegrationLogoProps) {
  const s = size;
  const wrap = (bg: string, children: React.ReactNode) => (
    <svg width={s} height={s} viewBox="0 0 32 32" fill="none" aria-hidden="true" className="integration-logo-svg">
      <rect width="32" height="32" rx="8" fill={bg} />
      {children}
    </svg>
  );

  switch (id) {
    case "gemini":
    case "image_gen":
      return wrap("#0B1324", (
        <path d="M16 5C16.8 11.4 20.6 15.2 27 16C20.6 16.8 16.8 20.6 16 27C15.2 20.6 11.4 16.8 5 16C11.4 15.2 15.2 11.4 16 5Z" fill="#38BDF8" />
      ));
    case "openai":
      return wrap("#101720", (
        <>
          <circle cx="16" cy="16" r="7.5" stroke="#E2E8F0" strokeWidth="1.8" />
          <path d="M16 8.5V23.5M9.5 12.2L22.5 19.8M22.5 12.2L9.5 19.8" stroke="#E2E8F0" strokeWidth="1.4" />
        </>
      ));
    case "anthropic":
      return wrap("#1A1410", (
        <path d="M11.2 23L16 9L20.8 23M13 18.5H19" stroke="#F59E0B" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
      ));
    case "ollama":
      return wrap("#11161E", (
        <>
          <circle cx="16" cy="17" r="6.5" stroke="#F1F5F9" strokeWidth="1.8" />
          <path d="M12.5 11.5L11 7.5M19.5 11.5L21 7.5" stroke="#F1F5F9" strokeWidth="1.8" strokeLinecap="round" />
          <circle cx="13.8" cy="16.5" r="1" fill="#F1F5F9" />
          <circle cx="18.2" cy="16.5" r="1" fill="#F1F5F9" />
        </>
      ));
    case "google_drive":
      return wrap("#0C1622", (
        <>
          <path d="M12.5 7H19.5L26 18.5H19L12.5 7Z" fill="#FBBF24" />
          <path d="M6 18.5L12.5 7L16 13L9.5 24.5L6 18.5Z" fill="#34D399" />
          <path d="M9.5 24.5L13 18.5H26L22.5 24.5H9.5Z" fill="#3B82F6" />
        </>
      ));
    case "google_gmail":
      return wrap("#1A0E12", (
        <>
          <rect x="6" y="9" width="20" height="14" rx="2.5" stroke="#F87171" strokeWidth="1.8" />
          <path d="M7 10.5L16 17L25 10.5" stroke="#F87171" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
        </>
      ));
    case "google_calendar":
      return wrap("#0C1829", (
        <>
          <rect x="7" y="8" width="18" height="17" rx="2.5" stroke="#60A5FA" strokeWidth="1.8" />
          <path d="M7 13H25M12 6V10M20 6V10" stroke="#60A5FA" strokeWidth="1.8" strokeLinecap="round" />
          <text x="16" y="22" textAnchor="middle" fill="#E2E8F0" fontSize="8" fontWeight="700" fontFamily="monospace">26</text>
        </>
      ));
    case "google_docs":
      return wrap("#0C1829", (
        <>
          <path d="M10 6H18L23 11V25C23 25.6 22.6 26 22 26H10C9.4 26 9 25.6 9 25V7C9 6.4 9.4 6 10 6Z" stroke="#60A5FA" strokeWidth="1.7" />
          <path d="M12 15H20M12 19H20M12 22.5H17" stroke="#93C5FD" strokeWidth="1.6" strokeLinecap="round" />
        </>
      ));
    case "google_sheets":
      return wrap("#0A1D16", (
        <>
          <rect x="8" y="7" width="16" height="18" rx="2" stroke="#34D399" strokeWidth="1.7" />
          <path d="M8 13H24M8 19H24M15 13V25" stroke="#34D399" strokeWidth="1.4" />
        </>
      ));
    case "google_slides":
      return wrap("#1E180B", (
        <>
          <rect x="7" y="9" width="18" height="14" rx="2" stroke="#FBBF24" strokeWidth="1.7" />
          <rect x="11" y="13" width="10" height="6" rx="1" fill="#FBBF24" fillOpacity="0.35" />
        </>
      ));
    case "google_cloud":
      return wrap("#0D1726", (
        <path d="M11 22H22C24.2 22 26 20.2 26 18C26 15.9 24.4 14.2 22.4 14C21.8 10.9 19.1 8.5 15.8 8.5C12.3 8.5 9.5 11.2 9.2 14.6C7.4 15.1 6 16.7 6 18.6C6 20.5 7.5 22 9.4 22H11Z" stroke="#60A5FA" strokeWidth="1.8" strokeLinejoin="round" />
      ));
    case "google_search":
      return wrap("#0C1624", (
        <>
          <circle cx="14.5" cy="14.5" r="6" stroke="#38BDF8" strokeWidth="2" />
          <path d="M19.2 19.2L24.5 24.5" stroke="#34D399" strokeWidth="2.2" strokeLinecap="round" />
        </>
      ));
    case "github":
      return wrap("#0E1117", (
        <path fillRule="evenodd" clipRule="evenodd" d="M16 6.5C10.7 6.5 6.5 10.8 6.5 16.1C6.5 20.3 9.2 23.9 13 25.2C13.5 25.3 13.7 25 13.7 24.7V22.9C11 23.5 10.5 21.8 10.5 21.8C10 20.7 9.4 20.4 9.4 20.4C8.5 19.8 9.5 19.8 9.5 19.8C10.5 19.9 11 20.8 11 20.8C11.8 22.3 13.2 21.9 13.7 21.6C13.8 21 14.1 20.6 14.3 20.3C12.2 20.1 10 19.2 10 15.6C10 14.6 10.4 13.7 11 13.1C10.9 12.8 10.6 11.8 11.1 10.5C11.1 10.5 11.9 10.2 13.7 11.5C14.5 11.3 15.2 11.2 16 11.2C16.8 11.2 17.5 11.3 18.3 11.5C20.1 10.2 20.9 10.5 20.9 10.5C21.4 11.8 21.1 12.8 21 13.1C21.6 13.7 22 14.6 22 15.6C22 19.2 19.8 20.1 17.7 20.3C18 20.6 18.3 21.2 18.3 22.1V24.7C18.3 25 18.5 25.3 19 25.2C22.8 23.9 25.5 20.3 25.5 16.1C25.5 10.8 21.3 6.5 16 6.5Z" fill="#F1F5F9" />
      ));
    case "vercel":
      return wrap("#0A0A0A", (
        <path d="M16 8L25 23.5H7L16 8Z" fill="#F8FAFC" />
      ));
    case "cloudflare":
      return wrap("#1B1209", (
        <path d="M8.5 21H23.5C24.9 21 26 19.9 26 18.5C26 17.2 25 16.1 23.7 16C23.4 13 20.8 10.8 17.7 10.8C15.1 10.8 12.9 12.4 12 14.7C11.5 14.5 11 14.4 10.4 14.4C8.4 14.4 6.8 16 6.8 18C6.8 19.7 7.5 21 8.5 21Z" fill="#F97316" />
      ));
    case "supabase":
      return wrap("#091B15", (
        <path d="M17.5 6.5L8.5 17.5H15.5L14.5 25.5L23.5 14.5H16.5L17.5 6.5Z" fill="#34D399" />
      ));
    case "postgresql":
      return wrap("#0D192B", (
        <>
          <ellipse cx="16" cy="11" rx="7.5" ry="3.5" stroke="#60A5FA" strokeWidth="1.7" />
          <path d="M8.5 11V21C8.5 22.9 11.9 24.5 16 24.5C20.1 24.5 23.5 22.9 23.5 21V11" stroke="#60A5FA" strokeWidth="1.7" />
          <path d="M8.5 16C8.5 17.9 11.9 19.5 16 19.5C20.1 19.5 23.5 17.9 23.5 16" stroke="#60A5FA" strokeWidth="1.4" />
        </>
      ));
    case "redis":
      return wrap("#1E0D10", (
        <>
          <path d="M16 8L25 12.5L16 17L7 12.5L16 8Z" fill="#F87171" />
          <path d="M7 16.5L16 21L25 16.5" stroke="#F87171" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
          <path d="M7 20.5L16 25L25 20.5" stroke="#FCA5A5" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
        </>
      ));
    case "gitlab":
      return wrap("#1D120C", (
        <path d="M16 24.5L7.5 18L10 9L12.8 15.5H19.2L22 9L24.5 18L16 24.5Z" stroke="#FB923C" strokeWidth="1.7" strokeLinejoin="round" />
      ));
    case "bitbucket":
      return wrap("#0B172A", (
        <path d="M8 9H24L21.8 23H10.2L8 9Z" stroke="#3B82F6" strokeWidth="1.8" strokeLinejoin="round" />
      ));
    case "replit":
      return wrap("#1C130C", (
        <>
          <rect x="9" y="8" width="6.5" height="5.5" rx="1" fill="#FB923C" />
          <rect x="16.5" y="13.5" width="6.5" height="5.5" rx="1" fill="#FB923C" />
          <rect x="9" y="19" width="6.5" height="5.5" rx="1" fill="#FB923C" />
        </>
      ));
    case "whatsapp":
      return wrap("#091E15", (
        <>
          <circle cx="16" cy="15.5" r="8" stroke="#34D399" strokeWidth="1.8" />
          <path d="M12.5 12.8C13.3 16.2 15.8 18.7 19.2 19.5" stroke="#34D399" strokeWidth="1.9" strokeLinecap="round" />
        </>
      ));
    case "telegram":
      return wrap("#0B1A26", (
        <path d="M24.5 9L7.5 15.8L13.5 17.8L15.8 23.5L18.8 19.8L22.5 22.5L24.5 9Z" stroke="#38BDF8" strokeWidth="1.6" strokeLinejoin="round" />
      ));
    case "slack":
      return wrap("#14151F", (
        <>
          <path d="M12 9V23M20 9V23M9 12H23M9 20H23" stroke="#94A3B8" strokeWidth="2" strokeLinecap="round" />
          <circle cx="12" cy="12" r="1.5" fill="#38BDF8" />
          <circle cx="20" cy="12" r="1.5" fill="#34D399" />
          <circle cx="12" cy="20" r="1.5" fill="#F87171" />
          <circle cx="20" cy="20" r="1.5" fill="#FBBF24" />
        </>
      ));
    case "discord":
      return wrap("#111427", (
        <>
          <path d="M9.5 11.5C11.5 10 13.5 9.8 16 9.8C18.5 9.8 20.5 10 22.5 11.5L24 21C22 22.4 19.8 22.8 18.5 22.8L17.4 20.8H14.6L13.5 22.8C12.2 22.8 10 22.4 8 21L9.5 11.5Z" stroke="#818CF8" strokeWidth="1.6" strokeLinejoin="round" />
          <circle cx="13" cy="16.5" r="1.2" fill="#E2E8F0" />
          <circle cx="19" cy="16.5" r="1.2" fill="#E2E8F0" />
        </>
      ));
    case "email_smtp":
      return wrap("#101722", (
        <>
          <rect x="6.5" y="9.5" width="19" height="13" rx="2" stroke="#94A3B8" strokeWidth="1.7" />
          <path d="M7.5 10.5L16 17L24.5 10.5" stroke="#38BDF8" strokeWidth="1.7" />
        </>
      ));
    case "notion":
      return wrap("#111317", (
        <>
          <rect x="7.5" y="7.5" width="17" height="17" rx="2.5" stroke="#E2E8F0" strokeWidth="1.7" />
          <path d="M12.5 20.5V11.5L19.5 20.5V11.5" stroke="#E2E8F0" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
        </>
      ));
    case "linear":
      return wrap("#101420", (
        <>
          <circle cx="16" cy="16" r="8" stroke="#94A3B8" strokeWidth="1.7" />
          <path d="M10.5 19.5L19.5 10.5M12.5 22L22 12.5" stroke="#38BDF8" strokeWidth="1.6" />
        </>
      ));
    case "trello":
      return wrap("#0B1A2A", (
        <>
          <rect x="7.5" y="7.5" width="17" height="17" rx="2.5" stroke="#38BDF8" strokeWidth="1.7" />
          <rect x="10.5" y="10.5" width="4.2" height="10" rx="1" fill="#38BDF8" />
          <rect x="17.3" y="10.5" width="4.2" height="6.5" rx="1" fill="#38BDF8" />
        </>
      ));
    case "asana":
      return wrap("#1D1014", (
        <>
          <circle cx="16" cy="11.5" r="2.7" fill="#FB7185" />
          <circle cx="11" cy="20" r="2.7" fill="#FB7185" />
          <circle cx="21" cy="20" r="2.7" fill="#FB7185" />
        </>
      ));
    case "jira":
      return wrap("#0B182C", (
        <path d="M16 7.5L23.5 15L16 22.5L12.5 19L16.5 15L12.5 11L16 7.5Z" fill="#60A5FA" />
      ));
    case "stripe":
      return wrap("#101528", (
        <path d="M19.8 12.2C19.8 11 18.6 10.3 16.5 10.3C14.2 10.3 12.5 11.4 12.5 13C12.5 16.5 19.8 15.2 19.8 19C19.8 20.9 18 22 15.5 22C13.4 22 12 21.3 11.4 20.6" stroke="#60A5FA" strokeWidth="2.2" strokeLinecap="round" />
      ));
    case "paystack":
      return wrap("#081B24", (
        <path d="M9 11H23M9 15.5H20M9 20H16.5" stroke="#38BDF8" strokeWidth="2.4" strokeLinecap="round" />
      ));
    case "flutterwave":
      return wrap("#1D150A", (
        <path d="M9 21C12 13 17 10 23 11C20 15 16 17 12 22" stroke="#FBBF24" strokeWidth="2.2" strokeLinecap="round" />
      ));
    case "spotify":
      return wrap("#091C12", (
        <>
          <circle cx="16" cy="16" r="8.5" stroke="#34D399" strokeWidth="1.7" />
          <path d="M11.5 13.5C14.8 12.5 18.2 12.8 20.8 14.3M12.2 16.8C14.9 16 17.7 16.3 19.8 17.5M13 19.8C15.1 19.3 17.2 19.5 18.8 20.4" stroke="#34D399" strokeWidth="1.5" strokeLinecap="round" />
        </>
      ));
    default:
      return wrap("#101622", (
        <>
          <circle cx="16" cy="16" r="6.5" stroke="#38BDF8" strokeWidth="1.6" />
          <circle cx="16" cy="16" r="2" fill="#38BDF8" />
        </>
      ));
  }
}
