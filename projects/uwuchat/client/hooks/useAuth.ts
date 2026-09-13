// Re-export the auth hook and LoadingScreen from the auth extension
// for use within the UwUchat project.  Keeps the cross-boundary
// import path in one place so the Vite project overlay plugin handles
// resolution correctly.
export { useAuth, LoadingScreen } from "../../../../extensions/auth/client/Provider";
