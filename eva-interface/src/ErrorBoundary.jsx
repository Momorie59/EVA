import { Component } from "react";

// Si une carte plante, on l'affiche calmement au lieu d'effacer toute la page.
export default class ErrorBoundary extends Component {
  state = { err: null };
  static getDerivedStateFromError(err) { return { err }; }
  componentDidUpdate(prev) { if (prev.resetKey !== this.props.resetKey && this.state.err) this.setState({ err: null }); }
  render() {
    if (!this.state.err) return this.props.children;
    return (
      <div className="card" role="alert" data-testid="page-error">
        <span className="card__label">Oups</span>
        <p className="page__warn">Cette page a rencontré un problème d'affichage : {String(this.state.err?.message || this.state.err)}</p>
        <button className="btn btn--primary" onClick={() => this.setState({ err: null })}>Réessayer</button>
      </div>
    );
  }
}
