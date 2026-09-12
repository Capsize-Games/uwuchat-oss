/**
 * Extension route elements for the auth extension.
 *
 * Re-exported as an array so the Vite plugin can spread them into
 * the root <Routes> component.
 */
import { Route } from "react-router-dom";
import LoginPage from "./components/LoginPage";
import RegisterPage from "./components/RegisterPage";
import VerifyPage from "./components/VerifyPage";
import OAuthCallbackPage from "./components/OAuthCallbackPage";

export const extensionRouteElements = [
  <Route key="login" path="/login" element={<LoginPage />} />,
  <Route key="register" path="/register" element={<RegisterPage />} />,
  <Route key="verify" path="/verify" element={<VerifyPage />} />,
  <Route key="oauth-callback" path="/oauth/callback" element={<OAuthCallbackPage />} />,
];
